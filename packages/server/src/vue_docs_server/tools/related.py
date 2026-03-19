"""vue_get_related tool — find related documentation for a Vue.js topic."""

from typing import Annotated

from fastmcp import Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from vue_docs_core.config import VUE_DOCS_BASE_URL
from vue_docs_server.startup import state


async def vue_get_related(
    topic: Annotated[
        str,
        Field(
            description="A Vue.js API name, concept, or topic to find related documentation for. "
            "Examples: 'ref', 'reactivity', 'component lifecycle', 'Transition', "
            "'two-way binding'."
        ),
    ],
    ctx: Context = None,
) -> str:
    """Find related Vue.js documentation for a given topic or API name.

    Uses entity matching, synonym resolution, and the API relationship
    graph to discover related concepts, APIs, and documentation pages.
    """
    if not state.is_ready:
        raise ToolError("Server not initialized. Please try again shortly.")

    if state.entity_matcher is None:
        raise ToolError("Entity matcher not available.")

    # Match the topic against the entity dictionary + synonyms
    match_result = state.entity_matcher.match(topic)

    if not match_result.entities:
        return (
            f"No matching APIs or concepts found for `{topic}`.\n\n"
            f'**Next step:** Use `vue_docs_search` with query `"{topic}"` '
            f"for a broader documentation search."
        )

    lines: list[str] = [f'# Related documentation for "{topic}"\n']

    # Collect all related entities
    seen: set[str] = set()
    related_entities: list[str] = []

    for entity_name in match_result.entities:
        entity = state.entity_index.entities.get(entity_name)
        if entity is None:
            continue

        seen.add(entity_name)
        type_label = entity.entity_type.replace("_", " ").title()

        # Direct match as a subsection
        lines.append(f"## `{entity_name}`\n")
        lines.append(f"> **{type_label}**")

        if entity.page_path:
            page = entity.page_path.removeprefix("/").removesuffix(".md")
            lines[-1] += f" — [{page}]({VUE_DOCS_BASE_URL}/{page})"

        lines.append("")

        # Gather related APIs
        if entity.related:
            for r in entity.related:
                if r not in seen:
                    related_entities.append(r)
                    seen.add(r)

    # Show related APIs in a table
    if related_entities:
        lines.append("## Related APIs\n")
        lines.append("| API | Type | Documentation |")
        lines.append("|-----|------|---------------|")
        for rel_name in related_entities:
            rel_entity = state.entity_index.entities.get(rel_name)
            if rel_entity:
                type_label = rel_entity.entity_type.replace("_", " ").title()
                if rel_entity.page_path:
                    page = rel_entity.page_path.removeprefix("/").removesuffix(".md")
                    doc_link = f"[{page}]({VUE_DOCS_BASE_URL}/{page})"
                else:
                    doc_link = "—"
                lines.append(f"| `{rel_name}` | {type_label} | {doc_link} |")
            else:
                lines.append(f"| `{rel_name}` | — | — |")
        lines.append("")

    # Next steps
    lines.append("---\n")
    lines.append("**Next steps:**")
    api_names = list(seen)[:3]
    lines.append(f'- `vue_docs_search` with query `"{topic}"` for full documentation content')
    for name in api_names:
        lines.append(f'- `vue_api_lookup` on `"{name}"` for API details')

    return "\n".join(lines)
