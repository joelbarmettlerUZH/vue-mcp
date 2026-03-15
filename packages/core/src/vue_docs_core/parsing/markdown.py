"""Markdown file parser — converts .md files into structured Chunks.

Walks the markdown-it-py token stream to decompose a Vue documentation page
into section (H2), subsection (H3/H4), code-block, and image chunks, each
carrying full metadata for downstream retrieval and reconstruction.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType

_SLUG_RE = re.compile(r"\{#([\w-]+)\}\s*$")
_API_STYLE_OPEN_RE = re.compile(r'<div\s+class="(options-api|composition-api)"')
_DIV_CLOSE_RE = re.compile(r"^\s*</div>\s*$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _Heading:
    level: int
    text: str
    slug: str
    line: int  # 0-indexed


def _extract_slug(heading_text: str) -> tuple[str, str]:
    """Return *(clean_title, slug)* from text like ``'Title {#my-slug}'``."""
    m = _SLUG_RE.search(heading_text)
    if m:
        return heading_text[: m.start()].strip(), m.group(1)
    slug = re.sub(r"[^\w\s-]", "", heading_text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return heading_text.strip(), slug


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
    styles = {
        api_map[i]
        for i in range(start, min(end, len(api_map)))
        if api_map[i] != "both"
    }
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


def _find_preceding_prose(lines: list[str], fence_line: int, boundary: int) -> str:
    """Collect the prose paragraph immediately before a code fence."""
    collected: list[str] = []
    i = fence_line - 1
    while i >= boundary:
        stripped = lines[i].strip()
        if not stripped:
            if collected:
                break
            i -= 1
            continue
        if stripped.startswith(("#", "```", "<div", "</div")):
            break
        collected.insert(0, lines[i].rstrip())
        i -= 1
    return "\n".join(collected).strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_markdown_file(file_path: Path, docs_root: Path) -> list[Chunk]:
    """Parse a markdown file into structured :class:`Chunk` objects.

    Produces section chunks (H2), subsection chunks (H3/H4), code-block
    chunks, and image chunks — each with metadata for retrieval and
    reconstruction.

    Args:
        file_path: Absolute path to the ``.md`` file.
        docs_root: Root directory of the Vue docs source
                   (e.g. ``data/vue-docs/src/``).

    Returns:
        List of chunks in document order.
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

    # --- code blocks & images from token stream ---
    code_blocks: list[dict] = []
    image_refs: list[dict] = []

    for tok in tokens:
        if tok.type == "fence" and tok.map:
            code_blocks.append(
                {
                    "lang": tok.info.strip(),
                    "content": tok.content,
                    "start": tok.map[0],
                    "end": tok.map[1],
                }
            )
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
        sec_content = "\n".join(lines[sec_start:sec_end]).strip()
        sec_id = f"{file_stem}#{h2.slug}"
        sec_style = _section_api_style(api_map, sec_start, sec_end)
        sec_bc = _breadcrumb(page_title, h2.text)

        child_ids: list[str] = []

        # ---- subsection chunks (H3/H4 inside this H2) ----
        subs = [
            h for h in headings if h.level in (3, 4) and sec_start < h.line < sec_end
        ]
        for si, sh in enumerate(subs):
            sub_start = sh.line
            sub_end = sec_end
            for nxt in subs[si + 1 :]:
                if nxt.level <= sh.level:
                    sub_end = nxt.line
                    break

            sub_content = "\n".join(lines[sub_start:sub_end]).strip()
            sub_id = f"{file_stem}#{sh.slug}"
            sub_style = _section_api_style(api_map, sub_start, sub_end)
            sub_bc = _breadcrumb(page_title, h2.text, sh.text)
            sibs = [f"{file_stem}#{s.slug}" for s in subs if s is not sh]

            chunks.append(
                Chunk(
                    chunk_id=sub_id,
                    chunk_type=ChunkType.SUBSECTION,
                    content=sub_content,
                    metadata=ChunkMetadata(
                        file_path=str(rel),
                        folder_path=folder,
                        page_title=page_title,
                        section_title=h2.text,
                        subsection_title=sh.text,
                        breadcrumb=sub_bc,
                        content_type="text",
                        api_style=sub_style,
                        parent_chunk_id=sec_id,
                        sibling_chunk_ids=sibs,
                    ),
                    content_hash=_content_hash(sub_content),
                )
            )
            child_ids.append(sub_id)

        # ---- code-block chunks ----
        code_idx = 0
        for cb in code_blocks:
            if sec_start <= cb["start"] < sec_end:
                cb_id = f"{file_stem}#{h2.slug}-code-{code_idx}"
                cb_style = (
                    api_map[cb["start"]]
                    if cb["start"] < len(api_map)
                    else "both"
                )
                prose = _find_preceding_prose(lines, cb["start"], sec_start)

                chunks.append(
                    Chunk(
                        chunk_id=cb_id,
                        chunk_type=ChunkType.CODE_BLOCK,
                        content=cb["content"],
                        metadata=ChunkMetadata(
                            file_path=str(rel),
                            folder_path=folder,
                            page_title=page_title,
                            section_title=h2.text,
                            breadcrumb=sec_bc,
                            content_type="code",
                            language_tag=cb["lang"],
                            api_style=cb_style,
                            parent_chunk_id=sec_id,
                            preceding_prose=prose,
                        ),
                        content_hash=_content_hash(cb["content"]),
                    )
                )
                child_ids.append(cb_id)
                code_idx += 1

        # ---- image chunks ----
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
                child_ids.append(img_id)
                img_idx += 1

        # ---- the H2 section chunk itself ----
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
                    api_style=sec_style,
                    child_chunk_ids=child_ids,
                    sibling_chunk_ids=sibling_ids,
                ),
                content_hash=_content_hash(sec_content),
            )
        )

    # --- fallback: files without H2 headings ---
    if not h2s:
        content = raw.strip()
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
