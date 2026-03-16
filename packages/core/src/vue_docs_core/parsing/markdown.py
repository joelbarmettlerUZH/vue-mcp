"""Markdown file parser — converts .md files into structured Chunks.

Walks the markdown-it-py token stream to decompose a Vue documentation page
into **section-level** chunks (one per H2), each carrying full metadata for
downstream retrieval and reconstruction.

Design (Option A — section-only chunking):
  - The H2 section is the primary and *only* retrieval unit for text content.
  - Code blocks, subsection headings, tips, and warnings are kept inline in
    the section content — they are part of the narrative.
  - ``<div class="options-api/composition-api">`` wrapper divs and
    ``</div>`` closing tags are stripped from the content so the embedding
    sees clean prose + code without rendering directives.
  - Playground links are stripped (noise for retrieval).
  - Image references are extracted as separate chunks (they need special
    handling for multimodal search).
  - If a section exceeds ``MAX_SECTION_CHARS``, it is split at H3
    boundaries, with the section intro paragraph prepended for context.
"""

import hashlib
import re
from pathlib import Path
from typing import NamedTuple

from markdown_it import MarkdownIt

from vue_docs_core.config import MAX_SECTION_CHARS
from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType

_SLUG_RE = re.compile(r"\{#([\w-]+)\}\s*$")
_API_STYLE_OPEN_RE = re.compile(r'<div\s+class="(options-api|composition-api)"')
_DIV_CLOSE_RE = re.compile(r"^\s*</div>\s*$")
_PLAYGROUND_RE = re.compile(r"\[Try it in the Playground\]\([^)]+\)\s*")
_API_DIV_OPEN_RE = re.compile(r'^\s*<div\s+class="(options-api|composition-api)">\s*$')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class HeadingSlug(NamedTuple):
    """Cleaned heading text and its URL slug."""

    clean_text: str
    slug: str


class _Heading:
    __slots__ = ("level", "line", "slug", "text")

    def __init__(self, level: int, text: str, slug: str, line: int):
        self.level = level
        self.text = text
        self.slug = slug
        self.line = line


def _extract_slug(heading_text: str) -> HeadingSlug:
    """Return *(clean_title, slug)* from text like ``'Title {#my-slug}'``."""
    m = _SLUG_RE.search(heading_text)
    if m:
        return HeadingSlug(heading_text[: m.start()].strip(), m.group(1))
    slug = re.sub(r"[^\w\s-]", "", heading_text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return HeadingSlug(heading_text.strip(), slug)


def _extract_headings(tokens: list) -> list[_Heading]:
    """Walk the token stream and return all headings."""
    headings: list[_Heading] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open" and i + 1 < len(tokens):
            level = int(tok.tag[1])
            inline = tokens[i + 1]
            raw = inline.content if inline.type == "inline" else ""
            text, slug = _extract_slug(raw)
            line = tok.map[0] if tok.map else 0
            headings.append(_Heading(level=level, text=text, slug=slug, line=line))
        i += 1
    return headings


def _build_api_style_map(lines: list[str]) -> list[str]:
    """Return a per-line list of ``'options'``, ``'composition'``, or ``'both'``.

    Assumes that ``</div>`` on its own line always closes the most recent
    API-style ``<div>``.  This holds for the Vue documentation source.
    """
    result: list[str] = []
    stack: list[str] = []
    for line in lines:
        if m := _API_STYLE_OPEN_RE.search(line):
            style = "options" if "options" in m.group(1) else "composition"
            stack.append(style)
        elif _DIV_CLOSE_RE.match(line) and stack:
            stack.pop()
        result.append(stack[-1] if stack else "both")
    return result


def _section_api_style(api_map: list[str], start: int, end: int) -> str:
    """Aggregate API style for a range of lines."""
    styles = {api_map[i] for i in range(start, min(end, len(api_map))) if api_map[i] != "both"}
    if not styles:
        return "both"
    if styles == {"options"}:
        return "options"
    if styles == {"composition"}:
        return "composition"
    return "both"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _breadcrumb(*parts: str) -> str:
    return " > ".join(p for p in parts if p)


def _clean_section_content(lines: list[str], start: int, end: int) -> str:
    """Clean a section's raw lines for embedding.

    Strips:
      - ``<div class="options-api/composition-api">`` lines
      - Standalone ``</div>`` lines that close API divs
      - Playground links
      - Leading/trailing blank lines

    Keeps:
      - All prose, headings, code fences, tips/warnings, images
    """
    cleaned: list[str] = []
    api_div_depth = 0

    for i in range(start, end):
        line = lines[i]
        stripped = line.strip()

        # Track and remove API-style div wrappers
        if _API_DIV_OPEN_RE.match(stripped):
            api_div_depth += 1
            continue
        if _DIV_CLOSE_RE.match(stripped) and api_div_depth > 0:
            api_div_depth -= 1
            continue

        # Remove playground links
        if _PLAYGROUND_RE.search(line):
            line = _PLAYGROUND_RE.sub("", line)
            if not line.strip():
                continue

        cleaned.append(line)

    result = "\n".join(cleaned).strip()

    # Collapse runs of 3+ blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result


def _extract_section_code_langs(lines: list[str], start: int, end: int) -> list[str]:
    """Extract language tags from all fenced code blocks in a line range."""
    langs: list[str] = []
    for i in range(start, end):
        stripped = lines[i].strip()
        if stripped.startswith("```") and len(stripped) > 3:
            lang = stripped[3:].strip().split()[0] if stripped[3:].strip() else ""
            if lang:
                langs.append(lang)
    return langs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_markdown_file(file_path: Path, docs_root: Path) -> list[Chunk]:
    """Parse a markdown file into structured :class:`Chunk` objects.

    Produces section chunks (H2) as the primary retrieval unit. Code blocks,
    subsection headings, and other content are kept inline within sections.
    Images are extracted as separate chunks.

    Large sections (>{MAX_SECTION_CHARS} chars) are split at H3 boundaries.
    """
    raw = file_path.read_text(encoding="utf-8")
    lines = raw.split("\n")
    total = len(lines)

    rel = file_path.relative_to(docs_root)
    file_stem = str(rel.with_suffix(""))
    folder = str(rel.parent)

    md = MarkdownIt()
    tokens = md.parse(raw)

    api_map = _build_api_style_map(lines)
    headings = _extract_headings(tokens)

    # --- page title (H1) ---
    page_title = ""
    for h in headings:
        if h.level == 1:
            page_title = h.text
            break
    if not page_title:
        page_title = file_path.stem.replace("-", " ").title()

    # --- images from token stream ---
    image_refs: list[dict] = []
    for tok in tokens:
        if tok.type == "inline" and tok.children:
            for child in tok.children:
                if child.type == "image":
                    src = (child.attrs or {}).get("src", "")
                    image_refs.append(
                        {
                            "alt": child.content or "",
                            "src": src,
                            "line": tok.map[0] if tok.map else 0,
                        }
                    )

    # --- H2 section boundaries ---
    h2s = [h for h in headings if h.level == 2]
    chunks: list[Chunk] = []

    for idx, h2 in enumerate(h2s):
        sec_start = h2.line
        sec_end = h2s[idx + 1].line if idx + 1 < len(h2s) else total
        sec_id = f"{file_stem}#{h2.slug}"
        sec_style = _section_api_style(api_map, sec_start, sec_end)
        sec_bc = _breadcrumb(page_title, h2.text)

        # Collect code languages present in this section
        code_langs = _extract_section_code_langs(lines, sec_start, sec_end)

        # ---- image chunks (extracted separately) ----
        sec_image_ids: list[str] = []
        img_idx = 0
        for img in image_refs:
            if sec_start <= img["line"] < sec_end:
                img_id = f"{file_stem}#{h2.slug}-img-{img_idx}"
                ctx_start = max(sec_start, img["line"] - 2)
                ctx_end = min(sec_end, img["line"] + 3)
                context = "\n".join(lines[ctx_start:ctx_end]).strip()

                chunks.append(
                    Chunk(
                        chunk_id=img_id,
                        chunk_type=ChunkType.IMAGE,
                        content=f"![{img['alt']}]({img['src']})",
                        metadata=ChunkMetadata(
                            file_path=str(rel),
                            folder_path=folder,
                            page_title=page_title,
                            section_title=h2.text,
                            breadcrumb=sec_bc,
                            content_type="image",
                            parent_chunk_id=sec_id,
                            preceding_prose=context,
                        ),
                        content_hash=_content_hash(img["src"]),
                    )
                )
                sec_image_ids.append(img_id)
                img_idx += 1

        # ---- clean section content ----
        sec_content = _clean_section_content(lines, sec_start, sec_end)

        # ---- H3 subsections within this H2 (for splitting large sections) ---
        # Only split at H3 level, not H4 — H4s stay inline within their H3
        h3s = [h for h in headings if h.level == 3 and sec_start < h.line < sec_end]

        # ---- decide whether to split ----
        if len(sec_content) > MAX_SECTION_CHARS and h3s:
            # Split at H3 boundaries
            _emit_split_sections(
                chunks=chunks,
                lines=lines,
                sec_content=sec_content,
                h2=h2,
                h3s=h3s,
                sec_start=sec_start,
                sec_end=sec_end,
                file_stem=file_stem,
                folder=folder,
                rel=str(rel),
                page_title=page_title,
                api_map=api_map,
                sec_image_ids=sec_image_ids,
            )
        else:
            # Single section chunk
            sibling_ids = [f"{file_stem}#{s.slug}" for s in h2s if s is not h2]
            chunks.append(
                Chunk(
                    chunk_id=sec_id,
                    chunk_type=ChunkType.SECTION,
                    content=sec_content,
                    metadata=ChunkMetadata(
                        file_path=str(rel),
                        folder_path=folder,
                        page_title=page_title,
                        section_title=h2.text,
                        breadcrumb=sec_bc,
                        content_type="text",
                        language_tag=",".join(sorted(set(code_langs))) if code_langs else "",
                        api_style=sec_style,
                        child_chunk_ids=sec_image_ids,
                        sibling_chunk_ids=sibling_ids,
                    ),
                    content_hash=_content_hash(sec_content),
                )
            )

    # --- fallback: files without H2 headings ---
    if not h2s:
        content = _clean_section_content(lines, 0, total)
        slug = headings[0].slug if headings else file_path.stem
        chunk_id = f"{file_stem}#{slug}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                chunk_type=ChunkType.SECTION,
                content=content,
                metadata=ChunkMetadata(
                    file_path=str(rel),
                    folder_path=folder,
                    page_title=page_title,
                    section_title=page_title,
                    breadcrumb=page_title,
                    content_type="text",
                    api_style=_section_api_style(api_map, 0, total),
                ),
                content_hash=_content_hash(content),
            )
        )

    return chunks


def _emit_split_sections(
    *,
    chunks: list[Chunk],
    lines: list[str],
    sec_content: str,
    h2: _Heading,
    h3s: list[_Heading],
    sec_start: int,
    sec_end: int,
    file_stem: str,
    folder: str,
    rel: str,
    page_title: str,
    api_map: list[str],
    sec_image_ids: list[str],
) -> None:
    """Split a large section at H3 boundaries and emit subsection chunks.

    Each subsection gets the intro paragraph (text between the H2 heading
    and the first H3) prepended for context, so it can stand alone.
    """
    sec_id = f"{file_stem}#{h2.slug}"
    sec_bc = _breadcrumb(page_title, h2.text)

    # Intro: content between H2 and first H3
    intro_content = _clean_section_content(lines, sec_start, h3s[0].line)

    all_sub_ids: list[str] = []

    for si, h3 in enumerate(h3s):
        sub_start = h3.line
        sub_end = sec_end
        # Find the next heading at same or higher level
        for nxt in h3s[si + 1 :]:
            if nxt.level <= h3.level:
                sub_end = nxt.line
                break

        sub_content = _clean_section_content(lines, sub_start, sub_end)
        sub_id = f"{file_stem}#{h3.slug}"
        sub_style = _section_api_style(api_map, sub_start, sub_end)
        sub_bc = _breadcrumb(page_title, h2.text, h3.text)

        # Prepend intro for context
        if intro_content:
            full_content = f"{intro_content}\n\n{sub_content}"
        else:
            full_content = sub_content

        code_langs = _extract_section_code_langs(lines, sub_start, sub_end)
        sibs = [f"{file_stem}#{s.slug}" for s in h3s if s is not h3]

        chunks.append(
            Chunk(
                chunk_id=sub_id,
                chunk_type=ChunkType.SUBSECTION,
                content=full_content,
                metadata=ChunkMetadata(
                    file_path=rel,
                    folder_path=folder,
                    page_title=page_title,
                    section_title=h2.text,
                    subsection_title=h3.text,
                    breadcrumb=sub_bc,
                    content_type="text",
                    language_tag=",".join(sorted(set(code_langs))) if code_langs else "",
                    api_style=sub_style,
                    parent_chunk_id=sec_id,
                    sibling_chunk_ids=sibs,
                ),
                content_hash=_content_hash(full_content),
            )
        )
        all_sub_ids.append(sub_id)

    # Emit the parent section chunk if it has meaningful intro content.
    # If the intro is tiny (just heading + a line or two), the subsections
    # already carry the intro prepended, so a near-empty parent adds no value.
    _MIN_INTRO_CHARS = 100
    parent_content = intro_content if intro_content else sec_content
    if len(parent_content) >= _MIN_INTRO_CHARS:
        chunks.append(
            Chunk(
                chunk_id=sec_id,
                chunk_type=ChunkType.SECTION,
                content=parent_content,
                metadata=ChunkMetadata(
                    file_path=rel,
                    folder_path=folder,
                    page_title=page_title,
                    section_title=h2.text,
                    breadcrumb=sec_bc,
                    content_type="text",
                    api_style=_section_api_style(api_map, sec_start, sec_end),
                    child_chunk_ids=all_sub_ids + sec_image_ids,
                ),
                content_hash=_content_hash(parent_content),
            )
        )
