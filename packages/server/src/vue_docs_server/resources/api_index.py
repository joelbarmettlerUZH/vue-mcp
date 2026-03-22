"""API index resources — per-source entity index and per-entity details."""

from collections import defaultdict

from fastmcp.exceptions import ResourceError

from vue_docs_core.data.sources import SourceDefinition
from vue_docs_server.startup import state
from vue_docs_server.tools.api_lookup import _clean_section_title, _find_entity, _page_path_to_url
from vue_docs_server.tools.search import _tool_prefix


def make_api_index_resource(source_def: SourceDefinition):
    """Create a source-specific API index resource function."""
    source_name = source_def.name
    display = source_def.display_name
    prefix = _tool_prefix(source_name)

    async def api_index() -> str:
        entity_index = state.entity_indices.get(source_name)
        if not entity_index or not entity_index.entities:
            raise ResourceError(
                f"No {display} API entities loaded. Run the ingestion pipeline first."
            )

        by_type: dict[str, list[str]] = defaultdict(list)
        for name, entity in entity_index.entities.items():
            type_label = entity.entity_type.replace("_", " ").title()
            by_type[type_label].append(name)

        total = len(entity_index.entities)
        categories = len(by_type)

        lines: list[str] = [
            f"# {display} API Index\n",
            f"> **{total}** API entities across **{categories}** categories\n",
            f"Use `{prefix}_api_lookup` to get details for any entity, or read "
            f"`{source_name}://api/entities/{{name}}` as a resource.\n",
        ]

        for type_label in sorted(by_type.keys()):
            names = sorted(by_type[type_label])
            lines.append(f"## {type_label} ({len(names)})\n")
            lines.append(", ".join(f"`{n}`" for n in names))
            lines.append("")

        return "\n".join(lines)

    api_index.__name__ = f"{source_name}_api_index"
    api_index.__doc__ = f"Complete index of all {display} API entities, grouped by type."
    return api_index


def make_api_entity_resource(source_def: SourceDefinition):
    """Create a source-specific API entity resource function."""
    source_name = source_def.name
    display = source_def.display_name

    async def api_entity(name: str) -> str:
        entity_index = state.entity_indices.get(source_name)
        if entity_index is None:
            entity_index = state.entity_index

        entity = _find_entity(name, entity_index)
        if entity is None:
            available_sample = ", ".join(
                f"`{n}`" for n in sorted(entity_index.entities.keys())[:15]
            )
            raise ResourceError(
                f"API entity not found: `{name}`.\n\n"
                f"Read `{source_name}://api/index` for all entities.\n\n"
                f"Examples: {available_sample}"
            )

        type_label = entity.entity_type.replace("_", " ").title()
        chunk_ids = entity_index.entity_to_chunks.get(entity.name, [])

        lines: list[str] = [f"# `{entity.name}`\n"]

        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| **Type** | {type_label} |")

        if entity.page_path:
            url = _page_path_to_url(entity.page_path, source=source_name)
            page_uri = entity.page_path.removesuffix(".md")
            lines.append(f"| **Documentation** | [{url}]({url}) |")
            lines.append(f"| **Page resource** | `{source_name}://pages/{page_uri}` |")

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

    api_entity.__name__ = f"{source_name}_api_entity"
    api_entity.__doc__ = f"Detailed information about a specific {display} API entity."
    return api_entity
