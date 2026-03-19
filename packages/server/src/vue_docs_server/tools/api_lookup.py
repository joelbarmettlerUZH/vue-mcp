"""vue_api_lookup tool implementation.

Fast-path exact match for API references — bypasses vector search entirely,
goes straight to the API entity index and retrieves chunks by entity name.
"""

from typing import Annotated

from fastmcp import Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from vue_docs_core.config import VUE_DOCS_BASE_URL
from vue_docs_server.startup import state


async def vue_api_lookup(
    api_name: Annotated[
        str,
        Field(
            description="The Vue API name to look up. Examples: 'ref', 'computed', "
            "'defineProps', 'v-model', 'onMounted', 'watchEffect', "
            "'Transition', 'KeepAlive'. "
            "Read the vue://api/index resource to browse all available API names."
        ),
    ],
    ctx: Context = None,
) -> str:
    """Look up a Vue.js API by exact name.

    Fast-path for API references — returns the API's type, documentation
    page, section, and related APIs. Much faster than a full search when
    you know the API name.
    """
    if not state.is_ready:
        raise ToolError("Server not initialized. Please try again shortly.")

    # Try exact match first
    entity = _find_entity(api_name)

    if entity is None and state.entity_matcher is not None:
        # Try fuzzy matching via EntityMatcher
        match_result = state.entity_matcher.match(api_name)
        if match_result.entities:
            entity = _find_entity(match_result.entities[0])

    if entity is None:
        return (
            f"No API entity found for `{api_name}`.\n\n"
            f'**Next step:** Use `vue_docs_search` with query `"{api_name}"` '
            f"for a broader documentation search."
        )

    # Build response
    type_label = entity.entity_type.replace("_", " ").title()
    chunk_ids = state.entity_index.entity_to_chunks.get(entity.name, [])

    lines: list[str] = [
        f"# `{entity.name}`\n",
        f"> **{type_label}**",
    ]

    if entity.page_path:
        page_url = _page_path_to_url(entity.page_path)
        lines.append(f"> {page_url}")

    if entity.section:
        section_clean = _clean_section_title(entity.section)
        lines[-1] += f" — {section_clean}"

    lines.append("")

    # Details table
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

    # Next steps
    lines.append("**Next steps:**")
    lines.append(f'- `vue_docs_search` with query `"{entity.name}"` for full documentation content')
    if entity.related:
        related_names = ", ".join(f"`{r}`" for r in entity.related[:3])
        lines.append(f"- `vue_api_lookup` on related APIs: {related_names}")

    return "\n".join(lines)


def _find_entity(name: str):
    """Look up an entity by exact name (case-insensitive)."""
    # Try exact case first
    if name in state.entity_index.entities:
        return state.entity_index.entities[name]

    # Try case-insensitive
    name_lower = name.lower().strip().replace("`", "")
    for entity_name, entity in state.entity_index.entities.items():
        if entity_name.lower() == name_lower:
            return entity

    return None


def _page_path_to_url(page_path: str) -> str:
    """Convert a page_path like 'api/reactivity-core.md' to a docs URL."""
    path = page_path.removeprefix("/").removesuffix(".md")
    return f"{VUE_DOCS_BASE_URL}/{path}"


def _clean_section_title(section: str) -> str:
    """Remove {#anchor} markers and HTML tags from section titles."""
    import re

    # Remove backticks first (before HTML removal, since backtick-wrapped
    # content like `<Transition>` should be preserved as plain text)
    section = section.replace("`", "")
    # Remove {#...} anchor markers
    section = re.sub(r"\s*\{#[^}]+\}", "", section)
    # Remove HTML tags (like <sup> badges) — but only self-closing or
    # tags with attributes (to avoid stripping content like <Transition>)
    section = re.sub(r"<sup[^>]*>.*?</sup>", "", section)
    section = re.sub(r"<[^>]+/>", "", section)
    # Clean up whitespace
    section = re.sub(r"\s+", " ", section).strip()
    return section
