"""Search scopes resource — lists valid scope values for vue_docs_search."""

from fastmcp.exceptions import ResourceError

from vue_docs_server.startup import state


async def vue_search_scopes() -> str:
    """List all valid scope values for the vue_docs_search tool."""
    if not state.folder_structure:
        raise ResourceError("No documentation indexed yet.")

    # Collect all folder paths and their page counts
    folders: dict[str, int] = {}
    for folder, pages in state.folder_structure.items():
        if not folder:
            continue
        folders[folder] = len(pages)
        # Also add parent folders as valid scopes
        parts = folder.split("/")
        for i in range(1, len(parts)):
            parent = "/".join(parts[:i])
            if parent not in folders:
                folders[parent] = 0

    # Count pages per scope (including sub-folders)
    scope_counts: dict[str, int] = {}
    for scope in sorted(folders.keys()):
        count = sum(
            len(pages) for f, pages in state.folder_structure.items()
            if f == scope or f.startswith(scope + "/")
        )
        scope_counts[scope] = count

    lines: list[str] = [
        "# Valid Search Scopes\n",
        "Use these values for the `scope` parameter of `vue_docs_search`.\n",
        '| Scope | Pages | Description |',
        '|-------|-------|-------------|',
        f'| `"all"` | {len(state.page_paths)} | Search all documentation |',
    ]

    for scope in sorted(scope_counts.keys()):
        count = scope_counts[scope]
        desc = scope.replace("/", " > ").title()
        lines.append(f'| `"{scope}"` | {count} | {desc} |')

    return "\n".join(lines)
