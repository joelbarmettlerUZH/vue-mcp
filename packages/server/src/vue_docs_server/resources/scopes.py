"""Search scopes resource — lists valid scope values per source."""

from fastmcp.exceptions import ResourceError

from vue_docs_core.data.sources import SourceDefinition
from vue_docs_server.startup import state
from vue_docs_server.tools.search import _tool_prefix


def make_scopes_resource(source_def: SourceDefinition):
    """Create a source-specific search scopes resource function."""
    source_name = source_def.name
    display = source_def.display_name
    prefix = _tool_prefix(source_name)

    async def search_scopes() -> str:
        folders_map = state.folder_structures_by_source.get(source_name, {})
        page_paths = state.page_paths_by_source.get(source_name, [])
        if not folders_map:
            raise ResourceError(f"No {display} documentation indexed yet.")

        folders: dict[str, int] = {}
        for folder, pages in folders_map.items():
            if not folder:
                continue
            folders[folder] = len(pages)
            parts = folder.split("/")
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                if parent not in folders:
                    folders[parent] = 0

        scope_counts: dict[str, int] = {}
        for scope in sorted(folders.keys()):
            count = sum(
                len(pages)
                for f, pages in folders_map.items()
                if f == scope or f.startswith(scope + "/")
            )
            scope_counts[scope] = count

        lines: list[str] = [
            f"# {display} — Valid Search Scopes\n",
            f"Use these values for the `scope` parameter of `{prefix}_docs_search`.\n",
            "| Scope | Pages | Description |",
            "|-------|-------|-------------|",
            f'| `"all"` | {len(page_paths)} | Search all {display} documentation |',
        ]

        for scope in sorted(scope_counts.keys()):
            count = scope_counts[scope]
            desc = scope.replace("/", " > ").title()
            lines.append(f'| `"{scope}"` | {count} | {desc} |')

        return "\n".join(lines)

    search_scopes.__name__ = f"{source_name}_search_scopes"
    search_scopes.__doc__ = f"List all valid scope values for the {prefix}_docs_search tool."
    return search_scopes
