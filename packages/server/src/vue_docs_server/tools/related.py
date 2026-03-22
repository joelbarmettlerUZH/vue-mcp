"""Get-related tool — find related documentation for a topic, per-source or combined."""

from typing import Annotated

from fastmcp import Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from vue_docs_core.data.sources import SOURCE_REGISTRY, SourceDefinition
from vue_docs_server.startup import state
from vue_docs_server.tools.search import _tool_prefix


async def _do_get_related(
    topic: str,
    source: str | None = None,
    ctx: Context = None,
) -> str:
    """Shared get-related implementation. source=None uses combined matcher."""
    if not state.is_ready:
        raise ToolError("Server not initialized. Please try again shortly.")

    entity_matcher = state.entity_matchers.get(source) if source else state.entity_matcher
    entity_index = state.entity_indices.get(source) if source else state.entity_index
    if entity_index is None:
        entity_index = state.entity_index

    if entity_matcher is None:
        raise ToolError("Entity matcher not available.")

    match_result = entity_matcher.match(topic)

    prefix = _tool_prefix(source) if source else "ecosystem"
    search_tool = f"{prefix}_docs_search" if source else "ecosystem_search"

    if not match_result.entities:
        return (
            f"No matching APIs or concepts found for `{topic}`.\n\n"
            f'**Next step:** Use `{search_tool}` with query `"{topic}"` '
            f"for a broader documentation search."
        )

    lines: list[str] = [f'# Related documentation for "{topic}"\n']

    seen: set[str] = set()
    related_entities: list[str] = []

    for entity_name in match_result.entities:
        entity = entity_index.entities.get(entity_name)
        if entity is None:
            continue

        seen.add(entity_name)
        type_label = entity.entity_type.replace("_", " ").title()
        entity_source = getattr(entity, "source", source or "vue")
        source_def = SOURCE_REGISTRY.get(entity_source)
        base_url = source_def.base_url if source_def else "https://vuejs.org"

        lines.append(f"## `{entity_name}`\n")
        lines.append(f"> **{type_label}**")

        if entity.page_path:
            page = entity.page_path.removeprefix("/").removesuffix(".md")
            lines[-1] += f" — [{page}]({base_url}/{page})"

        lines.append("")

        if entity.related:
            for r in entity.related:
                if r not in seen:
                    related_entities.append(r)
                    seen.add(r)

    if related_entities:
        lines.append("## Related APIs\n")
        lines.append("| API | Type | Documentation |")
        lines.append("|-----|------|---------------|")
        for rel_name in related_entities:
            rel_entity = entity_index.entities.get(rel_name)
            if rel_entity:
                type_label = rel_entity.entity_type.replace("_", " ").title()
                rel_source = getattr(rel_entity, "source", source or "vue")
                rel_def = SOURCE_REGISTRY.get(rel_source)
                rel_base = rel_def.base_url if rel_def else "https://vuejs.org"
                if rel_entity.page_path:
                    page = rel_entity.page_path.removeprefix("/").removesuffix(".md")
                    doc_link = f"[{page}]({rel_base}/{page})"
                else:
                    doc_link = "—"
                lines.append(f"| `{rel_name}` | {type_label} | {doc_link} |")
            else:
                lines.append(f"| `{rel_name}` | — | — |")
        lines.append("")

    lines.append("---\n")
    lines.append("**Next steps:**")
    api_names = list(seen)[:3]
    lines.append(f'- `{search_tool}` with query `"{topic}"` for full documentation content')
    lookup_tool = f"{_tool_prefix(source)}_api_lookup" if source else search_tool
    for name in api_names:
        lines.append(f'- `{lookup_tool}` on `"{name}"` for API details')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-source tool factory
# ---------------------------------------------------------------------------


def make_related_tool(source_def: SourceDefinition):
    """Create a source-specific get-related tool function."""
    source_name = source_def.name
    display = source_def.display_name
    prefix = _tool_prefix(source_name)

    async def get_related(
        topic: Annotated[
            str,
            Field(
                description=f"A {display} API name, concept, or topic to find related "
                f"documentation for."
            ),
        ],
        ctx: Context = None,
    ) -> str:
        return await _do_get_related(topic, source=source_name, ctx=ctx)

    get_related.__name__ = f"{prefix}_get_related"
    get_related.__doc__ = (
        f"Find related {display} documentation for a given topic or API name.\n\n"
        f"Uses entity matching, synonym resolution, and the API relationship "
        f"graph to discover related concepts, APIs, and documentation pages."
    )
    return get_related
