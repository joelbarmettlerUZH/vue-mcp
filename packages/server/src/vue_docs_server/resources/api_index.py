"""API index resources — full entity index and per-entity details."""

from collections import defaultdict

from fastmcp.exceptions import ResourceError

from vue_docs_server.startup import state
from vue_docs_server.tools.api_lookup import _find_entity, _page_path_to_url, _clean_section_title


async def vue_api_index() -> str:
    """Complete index of all Vue.js API entities, grouped by type."""
    if not state.entity_index.entities:
        raise ResourceError("No API entities loaded. Run the ingestion pipeline first.")

    by_type: dict[str, list[str]] = defaultdict(list)
    for name, entity in state.entity_index.entities.items():
        type_label = entity.entity_type.replace("_", " ").title()
        by_type[type_label].append(name)

    lines: list[str] = [
        "# Vue.js API Index\n",
        f"**{len(state.entity_index.entities)} API entities** across "
        f"{len(by_type)} categories.\n",
        "Use `vue_api_lookup` to get details, or read `vue://api/entities/{{name}}`.\n",
    ]

    for type_label in sorted(by_type.keys()):
        names = sorted(by_type[type_label])
        lines.append(f"## {type_label} ({len(names)})\n")
        lines.append(", ".join(f"`{n}`" for n in names))
        lines.append("")

    return "\n".join(lines)


async def vue_api_entity(name: str) -> str:
    """Detailed information about a specific Vue.js API entity."""
    entity = _find_entity(name)
    if entity is None:
        available_sample = ", ".join(
            sorted(state.entity_index.entities.keys())[:15]
        )
        raise ResourceError(
            f"API entity not found: '{name}'. "
            f"Read vue://api/index for all entities. "
            f"Examples: {available_sample}"
        )

    parts: list[str] = [f"# `{entity.name}`\n"]
    parts.append(f"**Type:** {entity.entity_type.replace('_', ' ').title()}")

    if entity.page_path:
        url = _page_path_to_url(entity.page_path)
        parts.append(f"**Documentation:** {url}")
        page_uri = entity.page_path.removesuffix(".md")
        parts.append(f"**Page resource:** `vue://pages/{page_uri}`")

    if entity.section:
        parts.append(f"**Section:** {_clean_section_title(entity.section)}")

    if entity.related:
        parts.append(f"**Related APIs:** {', '.join(f'`{r}`' for r in entity.related)}")

    chunk_ids = state.entity_index.entity_to_chunks.get(entity.name, [])
    if chunk_ids:
        parts.append(f"\nReferenced in {len(chunk_ids)} documentation chunks.")

    return "\n".join(parts)
