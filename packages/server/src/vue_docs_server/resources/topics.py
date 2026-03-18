"""Table of contents resources — full TOC and per-section TOC."""

from fastmcp.exceptions import ResourceError

from vue_docs_server.startup import state


def _page_title(file_path: str) -> str:
    """Derive a human-readable title from a file path."""
    name = file_path.rsplit("/", 1)[-1].removesuffix(".md")
    return name.replace("-", " ").title()


def _build_toc(folders: dict[str, list[str]], *, show_header: bool = True) -> str:
    """Build a markdown TOC from a folder structure dict."""
    lines: list[str] = []

    if show_header:
        total_pages = sum(len(pages) for pages in folders.values())
        total_sections = len(folders)
        lines.append("# Vue.js Documentation — Table of Contents\n")
        lines.append(
            f"> **{total_pages}** pages across **{total_sections}** sections\n"
        )

    for folder in sorted(folders.keys()):
        pages = folders[folder]
        folder_display = folder.replace("/", " > ").title() if folder else "Root"
        lines.append(f"## {folder_display}\n")
        for page_path in sorted(pages):
            title = _page_title(page_path)
            uri_path = page_path.removesuffix(".md")
            lines.append(f"- [{title}](vue://pages/{uri_path})")
        lines.append("")

    return "\n".join(lines)


async def vue_table_of_contents() -> str:
    """Complete table of contents for the Vue.js documentation."""
    if not state.folder_structure:
        raise ResourceError("No documentation indexed yet. Run the ingestion pipeline first.")

    return _build_toc(state.folder_structure)


async def vue_section_topics(section: str) -> str:
    """Table of contents for a specific documentation section."""
    if not state.folder_structure:
        raise ResourceError("No documentation indexed yet.")

    # Find all folders that start with this section prefix
    matching: dict[str, list[str]] = {}
    for folder, pages in state.folder_structure.items():
        if folder == section or folder.startswith(section + "/"):
            matching[folder] = pages

    if not matching:
        available = sorted(set(f.split("/")[0] for f in state.folder_structure if f))
        raise ResourceError(
            f"Section not found: `{section}`.\n\n"
            f"Available top-level sections: {', '.join(f'`{s}`' for s in available)}"
        )

    return _build_toc(matching)
