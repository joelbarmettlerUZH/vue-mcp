"""API lookup tool — fast exact-match for API references, per-source or combined."""

import re
from typing import Annotated

from fastmcp import Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from vue_docs_core.data.sources import SOURCE_REGISTRY, SourceDefinition
from vue_docs_core.models.entity import EntityIndex
from vue_docs_server.startup import state
from vue_docs_server.tools.search import _tool_prefix
from vue_docs_server.usage import log_tool_call


def _find_entity(name: str, entity_index: EntityIndex | None = None):
    """Look up an entity by exact name (case-insensitive)."""
    idx = entity_index or state.entity_index
    if name in idx.entities:
        return idx.entities[name]

    name_lower = name.lower().strip().replace("`", "")
    for entity_name, entity in idx.entities.items():
        if entity_name.lower() == name_lower:
            return entity

    return None


def _page_path_to_url(page_path: str, source: str = "vue") -> str:
    """Convert a page_path to a docs URL using the source's base_url."""
    source_def = SOURCE_REGISTRY.get(source)
    base_url = source_def.base_url if source_def else "https://vuejs.org"
    path = page_path.removeprefix("/").removesuffix(".md")
    return f"{base_url}/{path}"


def _clean_section_title(section: str) -> str:
    """Remove {#anchor} markers and HTML tags from section titles."""
    section = section.replace("`", "")
    section = re.sub(r"\s*\{#[^}]+\}", "", section)
    section = re.sub(r"<sup[^>]*>.*?</sup>", "", section)
    section = re.sub(r"<[^>]+/>", "", section)
    section = re.sub(r"\s+", " ", section).strip()
    return section


async def _do_api_lookup(
    api_name: str,
    source: str | None = None,
    ctx: Context = None,
) -> str:
    """Shared API lookup implementation. source=None searches combined index."""
    if not state.is_ready:
        raise ToolError("Server not initialized. Please try again shortly.")

    entity_index = state.entity_indices.get(source) if source else state.entity_index
    if entity_index is None:
        entity_index = state.entity_index

    entity_matcher = state.entity_matchers.get(source) if source else state.entity_matcher

    # Try exact match first
    entity = _find_entity(api_name, entity_index)

    if entity is None and entity_matcher is not None:
        match_result = entity_matcher.match(api_name)
        if match_result.entities:
            entity = _find_entity(match_result.entities[0], entity_index)

    # Determine tool names based on source
    prefix = _tool_prefix(source) if source else "ecosystem"
    search_tool = f"{prefix}_docs_search" if source else "ecosystem_search"

    if entity is None:
        return (
            f"No API entity found for `{api_name}`.\n\n"
            f'**Next step:** Use `{search_tool}` with query `"{api_name}"` '
            f"for a broader documentation search."
        )

    # Determine source for URL from entity
    entity_source = getattr(entity, "source", source or "vue")
    type_label = entity.entity_type.replace("_", " ").title()
    chunk_ids = entity_index.entity_to_chunks.get(entity.name, [])

    lines: list[str] = [
        f"# `{entity.name}`\n",
        f"> **{type_label}**",
    ]

    if entity.page_path:
        page_url = _page_path_to_url(entity.page_path, source=entity_source)
        lines.append(f"> {page_url}")

    if entity.section:
        section_clean = _clean_section_title(entity.section)
        lines[-1] += f" — {section_clean}"

    lines.append("")

    details: list[tuple[str, str]] = []
    if chunk_ids:
        details.append(("Documentation chunks", str(len(chunk_ids))))
    if entity.related:
        details.append(("Related APIs", ", ".join(f"`{r}`" for r in entity.related)))

    if details:
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        for key, val in details:
            lines.append(f"| {key} | {val} |")
        lines.append("")

    lines.append("**Next steps:**")
    lines.append(f'- `{search_tool}` with query `"{entity.name}"` for full documentation content')
    if entity.related:
        lookup_tool = f"{_tool_prefix(source)}_api_lookup" if source else search_tool
        related_names = ", ".join(f"`{r}`" for r in entity.related[:3])
        lines.append(f"- `{lookup_tool}` on related APIs: {related_names}")

    result = "\n".join(lines)
    log_tool_call(
        "api_lookup", query=api_name, framework=source, latency_ms=0, response_chars=len(result)
    )
    return result


# ---------------------------------------------------------------------------
# Per-source tool factory
# ---------------------------------------------------------------------------


def make_api_lookup_tool(source_def: SourceDefinition):
    """Create a source-specific API lookup tool function."""
    source_name = source_def.name
    display = source_def.display_name
    prefix = _tool_prefix(source_name)

    async def api_lookup(
        api_name: Annotated[
            str,
            Field(
                description=f"The {display} API name to look up. "
                f"Read the {source_name}://api/index resource to browse all available API names."
            ),
        ],
        ctx: Context = None,
    ) -> str:
        return await _do_api_lookup(api_name, source=source_name, ctx=ctx)

    api_lookup.__name__ = f"{prefix}_api_lookup"
    api_lookup.__doc__ = (
        f"Look up a {display} API by exact name.\n\n"
        f"Fast-path for API references — returns the API's type, documentation "
        f"page, section, and related APIs. Much faster than a full search when "
        f"you know the API name."
    )
    return api_lookup
