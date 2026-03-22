"""Table of contents resources — per-source TOC and section TOC."""

from fastmcp.exceptions import ResourceError

from vue_docs_core.data.sources import SourceDefinition
from vue_docs_server.startup import state


def _page_title(file_path: str) -> str:
    """Derive a human-readable title from a file path."""
    name = file_path.rsplit("/", 1)[-1].removesuffix(".md")
    return name.replace("-", " ").title()


def _build_toc(
    folders: dict[str, list[str]],
    *,
    source_name: str = "vue",
    display_name: str = "Vue.js",
    show_header: bool = True,
) -> str:
    """Build a markdown TOC from a folder structure dict."""
    lines: list[str] = []

    if show_header:
        total_pages = sum(len(pages) for pages in folders.values())
        total_sections = len(folders)
        lines.append(f"# {display_name} Documentation — Table of Contents\n")
        lines.append(f"> **{total_pages}** pages across **{total_sections}** sections\n")

    for folder in sorted(folders.keys()):
        pages = folders[folder]
        folder_display = folder.replace("/", " > ").title() if folder else "Root"
        lines.append(f"## {folder_display}\n")
        for page_path in sorted(pages):
            title = _page_title(page_path)
            uri_path = page_path.removesuffix(".md")
            lines.append(f"- [{title}]({source_name}://pages/{uri_path})")
        lines.append("")

    return "\n".join(lines)


def make_toc_resource(source_def: SourceDefinition):
    """Create a source-specific table-of-contents resource function."""
    source_name = source_def.name
    display = source_def.display_name

    async def table_of_contents() -> str:
        folders = state.folder_structures_by_source.get(source_name, {})
        if not folders:
            raise ResourceError(
                f"No {display} documentation indexed yet. Run the ingestion pipeline first."
            )
        return _build_toc(folders, source_name=source_name, display_name=display)

    table_of_contents.__name__ = f"{source_name}_table_of_contents"
    table_of_contents.__doc__ = f"Complete table of contents for the {display} documentation."
    return table_of_contents


def make_section_topics_resource(source_def: SourceDefinition):
    """Create a source-specific section topics resource function."""
    source_name = source_def.name
    display = source_def.display_name

    async def section_topics(section: str) -> str:
        folders = state.folder_structures_by_source.get(source_name, {})
        if not folders:
            raise ResourceError(f"No {display} documentation indexed yet.")

        matching: dict[str, list[str]] = {}
        for folder, pages in folders.items():
            if folder == section or folder.startswith(section + "/"):
                matching[folder] = pages

        if not matching:
            available = sorted(set(f.split("/")[0] for f in folders if f))
            raise ResourceError(
                f"Section not found: `{section}`.\n\n"
                f"Available top-level sections: {', '.join(f'`{s}`' for s in available)}"
            )

        return _build_toc(matching, source_name=source_name, display_name=display)

    section_topics.__name__ = f"{source_name}_section_topics"
    section_topics.__doc__ = f"Table of contents for a specific {display} documentation section."
    return section_topics
