"""Sort-key ordering, merge adjacent chunks, format response."""

from itertools import groupby

from vue_docs_core.clients.qdrant import SearchHit


# Base URL for Vue.js documentation
VUE_DOCS_BASE_URL = "https://vuejs.org"


def _file_path_to_url(file_path: str) -> str:
    """Convert a file path like 'guide/essentials/computed.md' to a docs URL."""
    path = file_path.removeprefix("/").removesuffix(".md")
    return f"{VUE_DOCS_BASE_URL}/{path}"


def _format_code_block(content: str, language: str) -> str:
    """Format a code block with fenced syntax."""
    lang = language or ""
    return f"```{lang}\n{content}\n```"


def _are_adjacent(a: SearchHit, b: SearchHit) -> bool:
    """Check whether two hits are adjacent chunks in the same section.

    Adjacent means: same file_path, same section_title, and consecutive
    sort keys (one immediately follows the other in document order).
    """
    pa, pb = a.payload, b.payload
    if pa.get("file_path") != pb.get("file_path"):
        return False
    if pa.get("section_title") != pb.get("section_title"):
        return False

    key_a = pa.get("global_sort_key", "")
    key_b = pb.get("global_sort_key", "")
    if not key_a or not key_b:
        return False

    # Adjacent if sort keys share the same prefix up to the last segment
    # and differ by exactly 1 in the last numeric segment.
    parts_a = key_a.rsplit("/", 1)
    parts_b = key_b.rsplit("/", 1)

    if len(parts_a) != len(parts_b):
        return False
    if len(parts_a) == 2 and parts_a[0] != parts_b[0]:
        return False

    # Extract numeric prefix from last segment (e.g. "03_computed" -> 3)
    last_a = parts_a[-1]
    last_b = parts_b[-1]
    try:
        num_a = int(last_a.split("_", 1)[0])
        num_b = int(last_b.split("_", 1)[0])
        return abs(num_a - num_b) == 1
    except (ValueError, IndexError):
        return False


def _merge_adjacent_hits(hits: list[SearchHit]) -> list[list[SearchHit]]:
    """Group consecutive adjacent hits into merged groups.

    Returns a list of groups where each group is a list of adjacent hits
    that should be rendered together.
    """
    if not hits:
        return []

    groups: list[list[SearchHit]] = [[hits[0]]]

    for hit in hits[1:]:
        if _are_adjacent(groups[-1][-1], hit):
            groups[-1].append(hit)
        else:
            groups.append([hit])

    return groups


def _build_summary_line(hits: list[SearchHit]) -> str:
    """Build a top-level summary describing what was found."""
    n = len(hits)
    pages = {h.payload.get("file_path", "") for h in hits}
    page_count = len(pages - {""})

    # Collect unique API entities across all hits
    all_entities: list[str] = []
    seen: set[str] = set()
    for h in hits:
        for e in h.payload.get("api_entities", []):
            if e not in seen:
                all_entities.append(e)
                seen.add(e)

    parts = [f"Found {n} relevant documentation section{'s' if n != 1 else ''}"]
    if page_count > 1:
        parts[0] += f" across {page_count} pages"

    if all_entities:
        entity_list = ", ".join(f"`{e}`" for e in all_entities[:8])
        if len(all_entities) > 8:
            entity_list += f" and {len(all_entities) - 8} more"
        parts.append(f"Related APIs: {entity_list}")

    return " | ".join(parts) + "\n"


def _render_hit(hit: SearchHit, show_heading: bool = True) -> list[str]:
    """Render a single hit into markdown lines.

    Args:
        hit: The search hit to render.
        show_heading: Whether to show the section/subsection heading.
            Set to False for non-first hits in a merged group.
    """
    parts: list[str] = []
    payload = hit.payload
    chunk_type = payload.get("chunk_type", "")
    breadcrumb = payload.get("breadcrumb", "")
    content = payload.get("content", "")
    section_title = payload.get("section_title", "")
    subsection_title = payload.get("subsection_title", "")
    language_tag = payload.get("language_tag", "")
    preceding_prose = payload.get("preceding_prose", "")
    api_entities = payload.get("api_entities", [])
    cross_references = payload.get("cross_references", [])

    # Section/subsection heading
    if show_heading:
        if subsection_title:
            parts.append(f"### {subsection_title}")
        elif section_title:
            parts.append(f"### {section_title}")

        if breadcrumb:
            parts.append(f"*{breadcrumb}*")
            parts.append("")

    # Content rendering based on chunk type
    if chunk_type == "code_block":
        if preceding_prose:
            parts.append(preceding_prose)
            parts.append("")
        parts.append(_format_code_block(content, language_tag))
    elif chunk_type == "image":
        # Render image with alt text; content holds the alt text or description
        alt = content or "documentation image"
        image_url = payload.get("image_url", "")
        if image_url:
            parts.append(f"![{alt}]({image_url})")
        else:
            parts.append(f"*[Image: {alt}]*")
        if preceding_prose:
            parts.append("")
            parts.append(preceding_prose)
    else:
        parts.append(content)

    # API entities tag line
    if api_entities:
        entities_str = ", ".join(f"`{e}`" for e in api_entities)
        parts.append(f"\nAPIs: {entities_str}")

    # Cross-reference "See also" links
    if cross_references:
        see_also = []
        for ref in cross_references[:5]:
            url = _file_path_to_url(ref) if ref.endswith(".md") else ref
            see_also.append(url)
        if see_also:
            parts.append(f"\nSee also: {', '.join(see_also)}")

    parts.append("")
    return parts


def reconstruct_results(
    hits: list[SearchHit],
    max_results: int = 3,
) -> str:
    """Reconstruct search hits into a readable, structured response.

    Groups results by source page, orders by global sort key (documentation
    reading order), merges adjacent chunks from the same section, and formats
    with breadcrumbs, code blocks, and cross-references.

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

    # Build summary
    summary = _build_summary_line(selected)

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

        # Merge adjacent hits
        merged_groups = _merge_adjacent_hits(page_hits)

        for merged in merged_groups:
            # First hit in group gets full heading
            page_parts.extend(_render_hit(merged[0], show_heading=True))
            # Subsequent adjacent hits skip the heading
            for hit in merged[1:]:
                page_parts.extend(_render_hit(hit, show_heading=False))

        sections.append("\n".join(page_parts))

    if not sections:
        return "No results found."

    return summary + "\n---\n\n".join(sections)
