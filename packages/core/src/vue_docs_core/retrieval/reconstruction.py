"""Sort-key ordering, merge adjacent chunks, format response."""

from itertools import groupby

from vue_docs_core.clients.qdrant import SearchHit
from vue_docs_core.config import VUE_DOCS_BASE_URL


def _file_path_to_url(file_path: str) -> str:
    """Convert a file path like 'guide/essentials/computed.md' to a docs URL."""
    path = file_path.removeprefix("/").removesuffix(".md")
    return f"{VUE_DOCS_BASE_URL}/{path}"


def _ref_to_link(ref: str) -> str:
    """Convert a cross-reference path to a named markdown link."""
    if ref.endswith(".md"):
        url = _file_path_to_url(ref)
        name = ref.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " ").title()
        return f"[{name}]({url})"
    return ref


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

    parts_a = key_a.rsplit("/", 1)
    parts_b = key_b.rsplit("/", 1)

    if len(parts_a) != len(parts_b):
        return False
    if len(parts_a) == 2 and parts_a[0] != parts_b[0]:
        return False

    last_a = parts_a[-1]
    last_b = parts_b[-1]
    try:
        num_a = int(last_a.split("_", 1)[0])
        num_b = int(last_b.split("_", 1)[0])
        return abs(num_a - num_b) == 1
    except (ValueError, IndexError):
        return False


def _merge_adjacent_hits(hits: list[SearchHit]) -> list[list[SearchHit]]:
    """Group consecutive adjacent hits into merged groups."""
    if not hits:
        return []

    groups: list[list[SearchHit]] = [[hits[0]]]

    for hit in hits[1:]:
        if _are_adjacent(groups[-1][-1], hit):
            groups[-1].append(hit)
        else:
            groups.append([hit])

    return groups


def _build_chunk_frontmatter(hits: list[SearchHit]) -> str:
    """Build YAML frontmatter for a chunk or merged group of chunks."""
    payload = hits[0].payload
    breadcrumb = payload.get("breadcrumb", "")
    file_path = payload.get("file_path", "")

    lines = ["---"]

    if breadcrumb:
        lines.append(f"breadcrumb: {breadcrumb}")

    if file_path:
        lines.append(f"source: {_file_path_to_url(file_path)}")

    # Collect APIs across all hits in the group
    all_apis: list[str] = []
    seen_apis: set[str] = set()
    all_refs: list[str] = []
    seen_refs: set[str] = set()

    for hit in hits:
        for api in hit.payload.get("api_entities", []):
            if api not in seen_apis:
                all_apis.append(api)
                seen_apis.add(api)
        for ref in hit.payload.get("cross_references", []):
            if ref not in seen_refs:
                all_refs.append(ref)
                seen_refs.add(ref)

    if all_apis:
        lines.append("apis: [" + ", ".join(all_apis) + "]")

    if all_refs:
        links = [_ref_to_link(r) for r in all_refs[:5]]
        lines.append("see_also: [" + ", ".join(links) + "]")

    lines.append("---")
    return "\n".join(lines)


def _render_hit(hit: SearchHit, show_heading: bool = True) -> list[str]:
    """Render a single hit's content into markdown lines (no frontmatter)."""
    parts: list[str] = []
    payload = hit.payload
    chunk_type = payload.get("chunk_type", "")
    content = payload.get("content", "")
    section_title = payload.get("section_title", "")
    subsection_title = payload.get("subsection_title", "")
    language_tag = payload.get("language_tag", "")
    preceding_prose = payload.get("preceding_prose", "")

    # Summary chunks as GFM admonitions
    if chunk_type in ("page_summary", "folder_summary", "top_summary"):
        label = {
            "page_summary": "Overview",
            "folder_summary": "Section Overview",
            "top_summary": "Topic Overview",
        }[chunk_type]
        parts.append("> [!NOTE]")
        parts.append(f"> **{label}:** {content}")
        parts.append("")
        return parts

    # Section/subsection heading
    if show_heading:
        heading = subsection_title or section_title
        if heading:
            parts.append(f"### {heading}")
            parts.append("")

    # Content rendering based on chunk type
    if chunk_type == "code_block":
        if preceding_prose:
            parts.append(preceding_prose)
            parts.append("")
        parts.append(_format_code_block(content, language_tag))
    elif chunk_type == "image":
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

    parts.append("")
    return parts


def reconstruct_results(
    hits: list[SearchHit],
    max_results: int = 3,
) -> str:
    """Reconstruct search hits into a readable, structured response.

    Groups results by source page, orders by global sort key (documentation
    reading order), merges adjacent chunks, and wraps each chunk group
    with YAML frontmatter containing its metadata.
    """
    if not hits:
        return "No results found."

    # Limit and sort by global_sort_key for documentation reading order
    selected = hits[:max_results]
    selected.sort(key=lambda h: h.payload.get("global_sort_key", "zzz"))

    # Separate folder/top summaries (no file_path) from page-level results
    _SUMMARY_TYPES = {"folder_summary", "top_summary"}
    high_level_summaries = [h for h in selected if h.payload.get("chunk_type") in _SUMMARY_TYPES]
    page_level_hits = [h for h in selected if h.payload.get("chunk_type") not in _SUMMARY_TYPES]

    sections: list[str] = []

    # Render high-level summaries first
    if high_level_summaries:
        for hl in high_level_summaries:
            parts = [_build_chunk_frontmatter([hl]), ""]
            parts.extend(_render_hit(hl, show_heading=True))
            sections.append("\n".join(parts))

    # Group by file_path (source page)
    for file_path, group in groupby(page_level_hits, key=lambda h: h.payload.get("file_path", "")):
        page_hits = list(group)
        if not page_hits:
            continue

        summaries = [h for h in page_hits if h.payload.get("chunk_type") == "page_summary"]
        detail_hits = [h for h in page_hits if h.payload.get("chunk_type") != "page_summary"]

        page_title = page_hits[0].payload.get("page_title", file_path)
        url = _file_path_to_url(file_path)

        # Page header
        page_parts: list[str] = [
            f"## {page_title}",
            f"<sup>[source]({url})</sup>",
            "",
        ]

        # Render page summaries
        for s in summaries:
            chunk_block = [_build_chunk_frontmatter([s]), ""]
            chunk_block.extend(_render_hit(s, show_heading=True))
            page_parts.extend(chunk_block)

        # Merge adjacent detail hits, then render each group with its own frontmatter
        merged_groups = _merge_adjacent_hits(detail_hits)

        for merged in merged_groups:
            # Frontmatter for the merged group
            page_parts.append(_build_chunk_frontmatter(merged))
            page_parts.append("")

            # Content: first hit gets heading, subsequent skip it
            page_parts.extend(_render_hit(merged[0], show_heading=True))
            for hit in merged[1:]:
                page_parts.extend(_render_hit(hit, show_heading=False))

        sections.append("\n".join(page_parts))

    if not sections:
        return "No results found."

    return "\n---\n\n".join(sections)
