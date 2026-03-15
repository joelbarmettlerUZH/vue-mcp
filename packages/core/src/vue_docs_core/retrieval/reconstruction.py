"""Sort-key ordering, merge adjacent chunks, format response."""

from itertools import groupby

from vue_docs_core.clients.qdrant import SearchHit


# Base URL for Vue.js documentation
VUE_DOCS_BASE_URL = "https://vuejs.org"


def _file_path_to_url(file_path: str) -> str:
    """Convert a file path like 'guide/essentials/computed.md' to a docs URL."""
    # Strip .md extension and leading slashes
    path = file_path.removeprefix("/").removesuffix(".md")
    return f"{VUE_DOCS_BASE_URL}/{path}"


def _format_code_block(content: str, language: str) -> str:
    """Format a code block with fenced syntax."""
    lang = language or ""
    return f"```{lang}\n{content}\n```"


def reconstruct_results(
    hits: list[SearchHit],
    max_results: int = 10,
) -> str:
    """Reconstruct search hits into a readable, structured response.

    Groups results by source page, orders by global sort key (documentation
    reading order), merges adjacent chunks, and formats with breadcrumbs
    and code blocks.

    Args:
        hits: Search hits from Qdrant hybrid search.
        max_results: Maximum number of chunks to include.

    Returns:
        Formatted markdown string with structured results.
    """
    if not hits:
        return "No results found."

    # Limit and sort by global_sort_key for documentation reading order
    selected = hits[:max_results]
    selected.sort(key=lambda h: h.payload.get("global_sort_key", "zzz"))

    # Group by file_path (source page)
    sections: list[str] = []

    for file_path, group in groupby(
        selected, key=lambda h: h.payload.get("file_path", "")
    ):
        page_hits = list(group)
        if not page_hits:
            continue

        page_title = page_hits[0].payload.get("page_title", file_path)
        url = _file_path_to_url(file_path)

        # Page header
        page_parts: list[str] = [f"## {page_title}"]
        page_parts.append(f"Source: {url}")
        page_parts.append("")

        for hit in page_hits:
            payload = hit.payload
            chunk_type = payload.get("chunk_type", "")
            breadcrumb = payload.get("breadcrumb", "")
            content = payload.get("content", "")
            section_title = payload.get("section_title", "")
            subsection_title = payload.get("subsection_title", "")
            language_tag = payload.get("language_tag", "")
            preceding_prose = payload.get("preceding_prose", "")
            api_entities = payload.get("api_entities", [])

            # Section/subsection heading
            if subsection_title:
                page_parts.append(f"### {subsection_title}")
            elif section_title:
                page_parts.append(f"### {section_title}")

            if breadcrumb:
                page_parts.append(f"*{breadcrumb}*")
                page_parts.append("")

            # Content rendering based on chunk type
            if chunk_type == "code_block":
                if preceding_prose:
                    page_parts.append(preceding_prose)
                    page_parts.append("")
                page_parts.append(_format_code_block(content, language_tag))
            else:
                page_parts.append(content)

            # API entities tag line
            if api_entities:
                entities_str = ", ".join(f"`{e}`" for e in api_entities)
                page_parts.append(f"\nAPIs: {entities_str}")

            page_parts.append("")

        sections.append("\n".join(page_parts))

    if not sections:
        return "No results found."

    # Build final response
    header = f"Found {len(selected)} relevant documentation sections:\n"
    return header + "\n---\n\n".join(sections)
