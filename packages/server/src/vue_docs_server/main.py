"""FastMCP app setup, tool/resource registration, and startup hooks."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.server.middleware.timing import DetailedTimingMiddleware

from vue_docs_core.config import settings
from vue_docs_core.data.sources import get_enabled_sources
from vue_docs_server.prompts import make_compare_prompt, make_debug_prompt, make_migrate_prompt
from vue_docs_server.resources.api_index import make_api_entity_resource, make_api_index_resource
from vue_docs_server.resources.pages import make_page_resource
from vue_docs_server.resources.scopes import make_scopes_resource
from vue_docs_server.resources.topics import make_section_topics_resource, make_toc_resource
from vue_docs_server.startup import hot_reload_loop, shutdown, startup
from vue_docs_server.tools.api_lookup import make_api_lookup_tool
from vue_docs_server.tools.related import make_related_tool
from vue_docs_server.tools.search import make_ecosystem_search_tool, make_search_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_instructions() -> str:
    """Build server instructions dynamically based on enabled sources."""
    sources = get_enabled_sources(settings.enabled_sources)

    lines: list[str] = [
        "This server provides comprehensive access to the Vue ecosystem documentation.",
        "",
        "## Tools",
        "",
        "Every tool takes a `framework` argument naming the documentation source to query.",
        "",
        "- `docs_search` — Semantic search across one framework's documentation",
        "- `api_lookup` — Fast exact-match API reference lookup",
        "- `get_related` — Find related APIs, concepts, and documentation pages",
    ]
    if len(sources) > 1:
        lines.append("- `ecosystem_search` — Search across all frameworks at once")
    lines.append("")

    lines.append("## Prompts (structured workflows)")
    lines.append("")
    lines.append("- `debug_issue` — Systematic debugging workflow")
    lines.append("- `compare_apis` — Side-by-side API/pattern comparison")
    lines.append("- `migrate_pattern` — Migration guide between patterns")
    lines.append("")

    lines.append("## Frameworks and resources")
    lines.append("")
    lines.append("Each framework exposes the same resources, under its own URI scheme:")
    lines.append("")
    lines.append("- `{framework}://topics` — Full table of contents")
    lines.append("- `{framework}://topics/{section}` — TOC for a specific section")
    lines.append("- `{framework}://pages/{path}` — Raw markdown of any doc page")
    lines.append("- `{framework}://api/index` — Complete API entity index")
    lines.append("- `{framework}://api/entities/{name}` — Details for a specific API")
    lines.append("- `{framework}://scopes` — Valid scope values for narrowing searches")
    lines.append("")
    lines.append("| `framework` | Documentation |")
    lines.append("|-------------|---------------|")
    for source_def in sources:
        lines.append(f"| `{source_def.name}` | {source_def.display_name} |")
    lines.append("")
    if len(sources) > 1:
        lines.append("Read `ecosystem://sources` for the list of available sources.")
        lines.append("")

    first_source = sources[0].name if sources else "vue"
    lines.append(
        f"Start by reading `{first_source}://topics` to understand the documentation structure, "
        f"then use the appropriate search tool for specific questions."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Server lifespan: startup and shutdown hooks."""
    startup()
    reload_task = asyncio.create_task(hot_reload_loop())
    logger.info("MCP server ready")
    yield
    reload_task.cancel()
    shutdown()


# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Vue Ecosystem MCP Server",
    instructions=_build_instructions(),
    lifespan=lifespan,
    mask_error_details=settings.mask_error_details,
    on_duplicate="warn",
)

# Middleware — order matters: outermost first
mcp.add_middleware(ErrorHandlingMiddleware(include_traceback=not settings.mask_error_details))
mcp.add_middleware(DetailedTimingMiddleware())
mcp.add_middleware(ResponseLimitingMiddleware(max_size=500_000))

_sources = get_enabled_sources(settings.enabled_sources)

# ---------------------------------------------------------------------------
# Tools and prompts: one framework-parameterised set, always visible
# ---------------------------------------------------------------------------
# Tool, resource and prompt lists must not vary per connection: the 2026-07-28 MCP
# spec has no sessions, so there is nowhere to remember a per-client selection.

_TOOL_ANNOTATIONS = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}

mcp.tool(
    name="docs_search",
    title="Search Documentation",
    tags={"search", "documentation"},
    annotations=_TOOL_ANNOTATIONS,
    timeout=30.0,
)(make_search_tool(_sources))

mcp.tool(
    name="api_lookup",
    title="API Lookup",
    tags={"api", "reference"},
    annotations=_TOOL_ANNOTATIONS,
    timeout=5.0,
)(make_api_lookup_tool(_sources))

mcp.tool(
    name="get_related",
    title="Find Related Topics",
    tags={"api", "discovery"},
    annotations=_TOOL_ANNOTATIONS,
    timeout=5.0,
)(make_related_tool(_sources))

mcp.prompt(
    name="debug_issue",
    title="Debug an Issue",
    tags={"debugging", "workflow"},
)(make_debug_prompt(_sources))

mcp.prompt(
    name="compare_apis",
    title="Compare APIs",
    tags={"comparison", "workflow"},
)(make_compare_prompt(_sources))

mcp.prompt(
    name="migrate_pattern",
    title="Migrate Patterns",
    tags={"migration", "workflow"},
)(make_migrate_prompt(_sources))

# ---------------------------------------------------------------------------
# Per-source resources (URI scheme per framework)
# ---------------------------------------------------------------------------

for _source_def in _sources:
    _sn = _source_def.name
    _display = _source_def.display_name

    mcp.resource(
        f"{_sn}://pages/{{path*}}",
        mime_type="text/markdown",
        tags={"content", "pages", _sn},
        title=f"{_display} Documentation Page",
    )(make_page_resource(_source_def))

    mcp.resource(
        f"{_sn}://topics",
        mime_type="text/markdown",
        tags={"navigation", "index", _sn},
        title=f"{_display} Table of Contents",
    )(make_toc_resource(_source_def))

    mcp.resource(
        f"{_sn}://topics/{{section*}}",
        mime_type="text/markdown",
        tags={"navigation", "index", _sn},
        title=f"{_display} Section Topics",
    )(make_section_topics_resource(_source_def))

    mcp.resource(
        f"{_sn}://api/index",
        mime_type="text/markdown",
        tags={"api", "index", _sn},
        title=f"{_display} API Entity Index",
    )(make_api_index_resource(_source_def))

    mcp.resource(
        f"{_sn}://api/entities/{{name}}",
        mime_type="text/markdown",
        tags={"api", "reference", _sn},
        title=f"{_display} API Entity Details",
    )(make_api_entity_resource(_source_def))

    mcp.resource(
        f"{_sn}://scopes",
        mime_type="text/markdown",
        tags={"navigation", "configuration", _sn},
        title=f"{_display} Valid Search Scopes",
    )(make_scopes_resource(_source_def))

# ---------------------------------------------------------------------------
# Cross-ecosystem: ecosystem search and sources resource
# ---------------------------------------------------------------------------

if len(_sources) > 1:
    mcp.tool(
        name="ecosystem_search",
        title="Search Vue Ecosystem",
        tags={"search", "documentation", "ecosystem"},
        annotations=_TOOL_ANNOTATIONS,
        timeout=30.0,
    )(make_ecosystem_search_tool())

    async def _ecosystem_sources() -> str:
        """List all available documentation sources in the Vue ecosystem."""
        lines = [
            "# Vue Ecosystem Documentation Sources\n",
            "| `framework` | Display Name | Base URL |",
            "|-------------|-------------|----------|",
        ]
        for src in _sources:
            lines.append(f"| `{src.name}` | {src.display_name} | {src.base_url} |")
        lines.append("")
        lines.append(
            "Pass the `framework` value to `docs_search`, `api_lookup` or `get_related`, "
            "or use `ecosystem_search` to search all of them at once."
        )
        return "\n".join(lines)

    mcp.resource(
        "ecosystem://sources",
        mime_type="text/markdown",
        tags={"navigation", "ecosystem"},
        title="Available Documentation Sources",
    )(_ecosystem_sources)


def main():
    """Run the MCP server."""
    if settings.server_transport == "stdio":
        mcp.run(transport="stdio")
        return
    mcp.run(
        transport=settings.server_transport,
        host=settings.server_host,
        port=settings.server_port,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
