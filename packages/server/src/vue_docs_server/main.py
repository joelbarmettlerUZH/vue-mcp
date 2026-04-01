"""FastMCP app setup, dynamic per-source registration, and startup hooks."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastmcp import Context, FastMCP
from fastmcp.resources.function_resource import FunctionResource
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.server.middleware.timing import DetailedTimingMiddleware
from fastmcp.server.transforms.visibility import Visibility

from vue_docs_core.config import settings
from vue_docs_core.data.sources import get_enabled_sources
from vue_docs_server.prompts import make_compare_prompt, make_debug_prompt, make_migrate_prompt
from vue_docs_server.resources.api_index import make_api_entity_resource, make_api_index_resource
from vue_docs_server.resources.pages import _do_read_page, make_page_resource
from vue_docs_server.resources.scopes import make_scopes_resource
from vue_docs_server.resources.topics import (
    _build_toc,
    make_section_topics_resource,
    make_toc_resource,
)
from vue_docs_server.startup import hot_reload_loop, shutdown, startup, state
from vue_docs_server.tools.api_lookup import (
    _clean_section_title,
    _find_entity,
    _page_path_to_url,
    make_api_lookup_tool,
)
from vue_docs_server.tools.related import make_related_tool
from vue_docs_server.tools.search import _tool_prefix, make_ecosystem_search_tool, make_search_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Default source that is always visible without explicit activation
_DEFAULT_SOURCE = "vue"


def _build_instructions() -> str:
    """Build server instructions dynamically based on enabled sources."""
    sources = get_enabled_sources(settings.enabled_sources)

    lines: list[str] = [
        "This server provides comprehensive access to the Vue ecosystem documentation.",
        "",
        "## Getting Started",
        "",
        "By default, only **Vue.js** documentation is active. If the project uses "
        "other Vue ecosystem frameworks, call `set_framework_preferences` first to "
        "activate them. Read `ecosystem://preferences` to see current settings.",
        "",
    ]

    for source_def in sources:
        sn = source_def.name
        display = source_def.display_name
        prefix = _tool_prefix(sn)
        active_note = "" if sn == _DEFAULT_SOURCE else " *(activate first)*"

        lines.append(f"## {display}{active_note}")
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
        lines.append("## Cross-Ecosystem (always visible)")
        lines.append("")
        lines.append("**Tools:**")
        lines.append("- `set_framework_preferences` — Activate/deactivate framework documentation")
        lines.append("- `ecosystem_search` — Search across all frameworks at once")
        lines.append("")
        lines.append("**Resources:**")
        lines.append("- `ecosystem://preferences` — Current active framework settings")
        lines.append("- `ecosystem://sources` — List all available documentation sources")
        lines.append("")

    first_source = sources[0].name if sources else "vue"
    lines.append(
        f"Start by reading `{first_source}://topics` to understand the documentation structure, "
        f"then use the appropriate search tool for specific questions."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Concrete resource enumeration (pages, entities, sections from DB state)
# ---------------------------------------------------------------------------

# Track URIs managed by _register_concrete_resources so we can prune stale ones.
_concrete_resource_uris: set[str] = set()


def _register_concrete_resources(app: FastMCP):
    """Register every known page, entity, and section as concrete MCP resources.

    Template resources (e.g. ``vue://pages/{path}``) remain as fallbacks, but
    LLMs cannot guess valid paths.  Concrete resources appear in
    ``list_resources`` so clients can discover them without searching first.

    On subsequent calls (hourly refresh), new resources are added and resources
    that no longer exist in the current state are removed.
    """
    sources = get_enabled_sources(settings.enabled_sources)
    current_uris: set[str] = set()
    added = 0

    for source_def in sources:
        sn = source_def.name
        display = source_def.display_name

        # --- Concrete page resources ---
        for page_path in state.page_paths_by_source.get(sn, []):
            uri_path = page_path.removesuffix(".md")
            uri = f"{sn}://pages/{uri_path}"
            current_uris.add(uri)
            added += _register_page(app, sn, display, page_path, uri_path)

        # --- Concrete API entity resources ---
        entity_index = state.entity_indices.get(sn)
        if entity_index:
            for entity_name in entity_index.entities:
                uri = f"{sn}://api/entities/{entity_name}"
                current_uris.add(uri)
                added += _register_entity(app, sn, display, entity_name)

        # --- Concrete section topics resources ---
        folders = state.folder_structures_by_source.get(sn, {})
        sections = sorted({f.split("/")[0] for f in folders if f})
        for section in sections:
            uri = f"{sn}://topics/{section}"
            current_uris.add(uri)
            added += _register_section(app, sn, display, section, folders)

    # Prune resources that were previously registered but no longer in state
    stale_uris = _concrete_resource_uris - current_uris
    if stale_uris:
        for uri in stale_uris:
            with contextlib.suppress(KeyError):
                app.local_provider.remove_resource(uri)
        logger.info("Removed %d stale concrete resources", len(stale_uris))

    _concrete_resource_uris.clear()
    _concrete_resource_uris.update(current_uris)

    logger.info("Concrete resources: %d total (%d new)", len(current_uris), added)


def _register_page(app: FastMCP, sn: str, display: str, page_path: str, uri_path: str) -> int:
    """Register a single concrete page resource. Returns 1 on success, 0 on skip."""
    _path, _source = page_path, sn

    async def read_page() -> str:
        return await _do_read_page(_path, _source)

    read_page.__name__ = f"{sn}_page_{uri_path.replace('/', '_')}"
    read_page.__doc__ = f"{display} doc page: {uri_path}"

    app.add_resource(
        FunctionResource.from_function(
            read_page,
            uri=f"{sn}://pages/{uri_path}",
            name=f"{sn}_page_{uri_path.replace('/', '_')}",
            title=uri_path.rsplit("/", 1)[-1].replace("-", " ").title(),
            description=f"{display} documentation page: {uri_path}",
            mime_type="text/markdown",
            tags={"content", "pages", sn},
        )
    )
    return 1


def _register_entity(app: FastMCP, sn: str, display: str, entity_name: str) -> int:
    """Register a single concrete API entity resource."""
    _name, _source = entity_name, sn

    async def read_entity() -> str:
        entity_index = state.entity_indices.get(_source)
        if entity_index is None:
            entity_index = state.entity_index
        entity = _find_entity(_name, entity_index)
        if entity is None:
            return f"Entity `{_name}` not found."

        type_label = entity.entity_type.replace("_", " ").title()
        chunk_ids = entity_index.entity_to_chunks.get(entity.name, [])
        lines: list[str] = [f"# `{entity.name}`\n"]
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| **Type** | {type_label} |")
        if entity.page_path:
            url = _page_path_to_url(entity.page_path, source=_source)
            page_uri = entity.page_path.removesuffix(".md")
            lines.append(f"| **Documentation** | [{url}]({url}) |")
            lines.append(f"| **Page resource** | `{_source}://pages/{page_uri}` |")
        if entity.section:
            lines.append(f"| **Section** | {_clean_section_title(entity.section)} |")
        if chunk_ids:
            lines.append(f"| **References** | {len(chunk_ids)} documentation chunks |")
        lines.append("")
        if entity.related:
            lines.append("## Related APIs\n")
            lines.append(", ".join(f"`{r}`" for r in entity.related))
            lines.append("")
        return "\n".join(lines)

    safe_name = entity_name.replace(" ", "_").replace("/", "_")
    read_entity.__name__ = f"{sn}_entity_{safe_name}"
    read_entity.__doc__ = f"{display} API entity: {entity_name}"

    app.add_resource(
        FunctionResource.from_function(
            read_entity,
            uri=f"{sn}://api/entities/{entity_name}",
            name=f"{sn}_entity_{safe_name}",
            title=entity_name,
            description=f"{display} API entity details: {entity_name}",
            mime_type="text/markdown",
            tags={"api", "reference", sn},
        )
    )
    return 1


def _register_section(
    app: FastMCP,
    sn: str,
    display: str,
    section: str,
    folders: dict[str, list[str]],
) -> int:
    """Register a single concrete section topics resource."""
    _section, _source, _display = section, sn, display

    async def read_section() -> str:
        current_folders = state.folder_structures_by_source.get(_source, {})
        matching = {
            f: p
            for f, p in current_folders.items()
            if f == _section or f.startswith(_section + "/")
        }
        if not matching:
            return f"Section `{_section}` not found."
        return _build_toc(matching, source_name=_source, display_name=_display)

    read_section.__name__ = f"{sn}_section_{section.replace('/', '_')}"
    read_section.__doc__ = f"{display} section topics: {section}"

    app.add_resource(
        FunctionResource.from_function(
            read_section,
            uri=f"{sn}://topics/{section}",
            name=f"{sn}_section_{section.replace('/', '_')}",
            title=f"{section.replace('/', ' > ').title()}",
            description=f"{display} documentation section: {section}",
            mime_type="text/markdown",
            tags={"navigation", "index", sn},
        )
    )
    return 1


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Server lifespan: startup and shutdown hooks."""
    startup()
    _register_concrete_resources(app)
    reload_task = asyncio.create_task(hot_reload_loop(lambda: _register_concrete_resources(app)))
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

# ---------------------------------------------------------------------------
# Visibility: hide non-default sources initially, per-session activation
# ---------------------------------------------------------------------------

_sources = get_enabled_sources(settings.enabled_sources)
_non_default_source_names = [s.name for s in _sources if s.name != _DEFAULT_SOURCE]

for _hidden_source in _non_default_source_names:
    mcp.add_transform(Visibility(False, tags={_hidden_source}))

# ---------------------------------------------------------------------------
# Dynamic per-source registration
# ---------------------------------------------------------------------------

_TOOL_ANNOTATIONS = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}

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
# Cross-ecosystem: preferences tool, ecosystem search, sources resource
# ---------------------------------------------------------------------------

# Build source info for preference tool descriptions
_source_info = {s.name: s.display_name for s in _sources}


@mcp.tool(
    name="set_framework_preferences",
    title="Set Framework Preferences",
    tags={"preferences", "ecosystem"},
    annotations={"readOnlyHint": False, "idempotentHint": True, "openWorldHint": False},
    timeout=5.0,
)
async def set_framework_preferences(
    vue: bool = True,
    vue_router: bool = False,
    vueuse: bool = False,
    vite: bool = False,
    vitest: bool = False,
    nuxt: bool = False,
    pinia: bool = False,
    ctx: Context = None,
) -> str:
    """Activate or deactivate Vue ecosystem framework documentation.

    Call this at the start of a session to match the project's tech stack.
    Only activated frameworks appear as tools, resources, and prompts.

    Vue is active by default. Set other frameworks to true to activate them.
    """
    prefs = {
        "vue": vue,
        "vue-router": vue_router,
        "vueuse": vueuse,
        "vite": vite,
        "vitest": vitest,
        "nuxt": nuxt,
        "pinia": pinia,
    }

    # Map param names to source registry names
    activated = []
    deactivated = []

    for source_name, enabled in prefs.items():
        if source_name not in _source_info:
            continue
        display = _source_info[source_name]
        if enabled:
            await ctx.enable_components(tags={source_name})
            activated.append(display)
        else:
            await ctx.disable_components(tags={source_name})
            deactivated.append(display)

    # Store preferences for the get resource
    await ctx.set_state("framework_preferences", prefs)

    lines = ["# Framework Preferences Updated\n"]
    if activated:
        lines.append(f"**Active:** {', '.join(activated)}")
    if deactivated:
        lines.append(f"**Inactive:** {', '.join(deactivated)}")
    lines.append("")
    lines.append("The available tools, resources, and prompts have been updated for this session.")
    return "\n".join(lines)


@mcp.resource(
    "ecosystem://preferences",
    mime_type="text/markdown",
    tags={"preferences", "ecosystem"},
    title="Framework Preferences",
)
async def _ecosystem_preferences() -> str:
    """Current framework activation settings for this session."""
    lines = [
        "# Framework Preferences\n",
        "| Framework | Status |",
        "|-----------|--------|",
    ]
    for source_def in _sources:
        is_default = source_def.name == _DEFAULT_SOURCE
        status = "Active (default)" if is_default else "Inactive"
        if not is_default:
            status += " — call `set_framework_preferences` to activate"
        lines.append(f"| {source_def.display_name} | {status} |")

    lines.append("")
    lines.append(
        "Call `set_framework_preferences` with the frameworks your project uses "
        "to activate their documentation, tools, and prompts."
    )
    return "\n".join(lines)


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
        lines.append("**Cross-ecosystem:** `ecosystem_search`, `set_framework_preferences`")
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
