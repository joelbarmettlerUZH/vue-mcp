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
            f"No matching APIs or concepts found for '{topic}'. "
            f"Try `vue_docs_search` for a broader documentation search."
        )

    parts: list[str] = [f'# Related documentation for "{topic}"\n']

    # Collect all related entities
    seen: set[str] = set()
    related_entities: list[str] = []

    for entity_name in match_result.entities:
        entity = state.entity_index.entities.get(entity_name)
        if entity is None:
            continue

        seen.add(entity_name)

        # Direct match info
        type_label = entity.entity_type.replace("_", " ").title()
        url = ""
        if entity.page_path:
            page = entity.page_path.removeprefix("/").removesuffix(".md")
            url = f" — [{page}]({VUE_DOCS_BASE_URL}/{page})"

        parts.append(f"## `{entity_name}` ({type_label}){url}\n")

        # Gather related APIs
        if entity.related:
            for r in entity.related:
                if r not in seen:
                    related_entities.append(r)
                    seen.add(r)

    # Show related APIs with their types
    if related_entities:
        parts.append("## Related APIs\n")
        for rel_name in related_entities:
            rel_entity = state.entity_index.entities.get(rel_name)
            if rel_entity:
                type_label = rel_entity.entity_type.replace("_", " ").title()
                parts.append(f"- `{rel_name}` ({type_label})")
            else:
                parts.append(f"- `{rel_name}`")
        parts.append("")

    # Suggest next steps
    parts.append("---")
    parts.append("Use `vue_docs_search` with these API names for full documentation content.")

    return "\n".join(parts)
