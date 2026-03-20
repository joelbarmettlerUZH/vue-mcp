"""FastMCP app setup, dynamic per-source registration, and startup hooks."""

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
from vue_docs_server.startup import data_reload_loop, shutdown, startup
from vue_docs_server.tools.api_lookup import make_api_lookup_tool
from vue_docs_server.tools.related import make_related_tool
from vue_docs_server.tools.search import _tool_prefix, make_ecosystem_search_tool, make_search_tool

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
    ]

    for source_def in sources:
        sn = source_def.name
        display = source_def.display_name
        prefix = _tool_prefix(sn)

        lines.append(f"## {display}")
        lines.append("")
        lines.append("**Resources** (browse without searching):")
        lines.append(f"- `{sn}://topics` — Full table of contents")
        lines.append(f"- `{sn}://topics/{{section}}` — TOC for a specific section")
        lines.append(f"- `{sn}://pages/{{path}}` — Raw markdown of any doc page")
        lines.append(f"- `{sn}://api/index` — Complete API entity index")
        lines.append(f"- `{sn}://api/entities/{{name}}` — Details for a specific API")
        lines.append(f"- `{sn}://scopes` — Valid scope values for narrowing searches")
        lines.append("")
        lines.append("**Tools** (for active retrieval):")
        lines.append(f"- `{prefix}_docs_search` — Semantic search across {display} documentation")
        lines.append(f"- `{prefix}_api_lookup` — Fast exact-match API reference lookup")
        lines.append(
            f"- `{prefix}_get_related` — Find related APIs, concepts, and documentation pages"
        )
        lines.append("")
        lines.append("**Prompts** (structured workflows):")
        lines.append(f"- `debug_{prefix}_issue` — Systematic {display} debugging workflow")
        lines.append(f"- `compare_{prefix}_apis` — Side-by-side API/pattern comparison")
        lines.append(f"- `migrate_{prefix}_pattern` — Migration guide between patterns")
        lines.append("")

    if len(sources) > 1:
        lines.append("## Cross-Ecosystem")
        lines.append("")
        lines.append("**Tools:**")
        lines.append("- `ecosystem_search` — Search across all frameworks at once")
        lines.append("")
        lines.append("**Resources:**")
        lines.append("- `ecosystem://sources` — List all available documentation sources")
        lines.append("")

    first_source = sources[0].name if sources else "vue"
    lines.append(
        f"Start by reading `{first_source}://topics` to understand the documentation structure, "
        f"then use the appropriate search tool for specific questions."
    )

    return "\n".join(lines)


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Server lifespan: startup and shutdown hooks."""
    startup()
    reload_task = asyncio.create_task(data_reload_loop())
    logger.info("MCP server ready")
    yield
    reload_task.cancel()
    shutdown()


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

# ---------------------------------------------------------------------------
# Dynamic per-source registration
# ---------------------------------------------------------------------------

_TOOL_ANNOTATIONS = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}

_sources = get_enabled_sources(settings.enabled_sources)

for _source_def in _sources:
    _sn = _source_def.name
    _display = _source_def.display_name
    _prefix = _tool_prefix(_sn)

    # Tools
    mcp.tool(
        name=f"{_prefix}_docs_search",
        title=f"Search {_display} Documentation",
        tags={"search", "documentation", _sn},
        annotations=_TOOL_ANNOTATIONS,
        timeout=30.0,
    )(make_search_tool(_source_def))

    mcp.tool(
        name=f"{_prefix}_api_lookup",
        title=f"{_display} API Lookup",
        tags={"api", "reference", _sn},
        annotations=_TOOL_ANNOTATIONS,
        timeout=5.0,
    )(make_api_lookup_tool(_source_def))

    mcp.tool(
        name=f"{_prefix}_get_related",
        title=f"Find Related {_display} Topics",
        tags={"api", "discovery", _sn},
        annotations=_TOOL_ANNOTATIONS,
        timeout=5.0,
    )(make_related_tool(_source_def))

    # Resources
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

    # Prompts
    mcp.prompt(
        name=f"debug_{_prefix}_issue",
        title=f"Debug a {_display} Issue",
        tags={"debugging", "workflow", _sn},
    )(make_debug_prompt(_source_def))

    mcp.prompt(
        name=f"compare_{_prefix}_apis",
        title=f"Compare {_display} APIs",
        tags={"comparison", "workflow", _sn},
    )(make_compare_prompt(_source_def))

    mcp.prompt(
        name=f"migrate_{_prefix}_pattern",
        title=f"Migrate {_display} Patterns",
        tags={"migration", "workflow", _sn},
    )(make_migrate_prompt(_source_def))

# ---------------------------------------------------------------------------
# Cross-ecosystem tools and resources (when multiple sources enabled)
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
            "| Source | Display Name | Base URL |",
            "|--------|-------------|----------|",
        ]
        for src in _sources:
            prefix = _tool_prefix(src.name)
            lines.append(f"| `{src.name}` | {src.display_name} | {src.base_url} |")
        lines.append("")
        lines.append("## Available per-source tools\n")
        for src in _sources:
            prefix = _tool_prefix(src.name)
            lines.append(
                f"**{src.display_name}:** `{prefix}_docs_search`, "
                f"`{prefix}_api_lookup`, `{prefix}_get_related`"
            )
        lines.append("")
        lines.append("**Cross-ecosystem:** `ecosystem_search`")
        return "\n".join(lines)

    mcp.resource(
        "ecosystem://sources",
        mime_type="text/markdown",
        tags={"navigation", "ecosystem"},
        title="Available Documentation Sources",
    )(_ecosystem_sources)


def main():
    """Run the MCP server."""
    mcp.run(
        transport=settings.server_transport,
        host=settings.server_host,
        port=settings.server_port,
    )


if __name__ == "__main__":
    main()
