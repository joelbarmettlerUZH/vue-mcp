"""API index resources — full entity index and per-entity details."""

from collections import defaultdict

from fastmcp.exceptions import ResourceError

from vue_docs_server.startup import state
from vue_docs_server.tools.api_lookup import _clean_section_title, _find_entity, _page_path_to_url


async def vue_api_index() -> str:
    """Complete index of all Vue.js API entities, grouped by type."""
    if not state.entity_index.entities:
        raise ResourceError("No API entities loaded. Run the ingestion pipeline first.")

    by_type: dict[str, list[str]] = defaultdict(list)
    for name, entity in state.entity_index.entities.items():
        type_label = entity.entity_type.replace("_", " ").title()
        by_type[type_label].append(name)

    total = len(state.entity_index.entities)
    categories = len(by_type)

    lines: list[str] = [
        "# Vue.js API Index\n",
        f"> **{total}** API entities across **{categories}** categories\n",
        "Use `vue_api_lookup` to get details for any entity, or read "
        "`vue://api/entities/{name}` as a resource.\n",
    ]

    for type_label in sorted(by_type.keys()):
        names = sorted(by_type[type_label])
        lines.append(f"## {type_label} ({len(names)})\n")
        # Render as a compact comma-separated list
        lines.append(", ".join(f"`{n}`" for n in names))
        lines.append("")

    return "\n".join(lines)


async def vue_api_entity(name: str) -> str:
    """Detailed information about a specific Vue.js API entity."""
    entity = _find_entity(name)
    if entity is None:
        available_sample = ", ".join(
            f"`{n}`" for n in sorted(state.entity_index.entities.keys())[:15]
        )
        raise ResourceError(
            f"API entity not found: `{name}`.\n\n"
            f"Read `vue://api/index` for all entities.\n\n"
            f"Examples: {available_sample}"
        )

    type_label = entity.entity_type.replace("_", " ").title()
    chunk_ids = state.entity_index.entity_to_chunks.get(entity.name, [])

    lines: list[str] = [f"# `{entity.name}`\n"]

    # Metadata table
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| **Type** | {type_label} |")

    if entity.page_path:
        url = _page_path_to_url(entity.page_path)
        page_uri = entity.page_path.removesuffix(".md")
        lines.append(f"| **Documentation** | [{url}]({url}) |")
        lines.append(f"| **Page resource** | `vue://pages/{page_uri}` |")

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
