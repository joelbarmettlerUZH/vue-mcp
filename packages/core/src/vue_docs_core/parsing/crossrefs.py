"""Internal link extraction and cross-reference classification.

Extracts markdown links from chunk content, resolves relative paths,
and classifies each reference as HIGH (guide↔api), MEDIUM (same folder),
or LOW (cross-folder) value.
"""

import re
from pathlib import PurePosixPath

from vue_docs_core.models.chunk import Chunk
from vue_docs_core.models.crossref import CrossRefType, CrossReference

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _resolve_target_path(raw_link: str, source_file: str) -> str | None:
    """Resolve a markdown link to a normalized doc-relative path.

    Returns ``None`` for external links and same-page anchors.
    """
    # Skip external
    if raw_link.startswith(("http://", "https://", "mailto:")):
        return None

    # Skip same-page anchors
    if raw_link.startswith("#"):
        return None

    # Strip anchor portion
    path = raw_link.split("#")[0]

    # Resolve relative links
    if path.startswith("/"):
        # Absolute site-root link
        path = path.lstrip("/")
    elif path.startswith("."):
        # Relative to source file's directory
        source_dir = str(PurePosixPath(source_file).parent)
        path = str(PurePosixPath(source_dir) / path)
        # Normalize .. and . segments
        parts: list[str] = []
        for seg in path.split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg != ".":
                parts.append(seg)
        path = "/".join(parts)
    else:
        # Bare relative (rare) — resolve same as ./
        source_dir = str(PurePosixPath(source_file).parent)
        path = str(PurePosixPath(source_dir) / path)

    # Strip .html / .md extensions
    path = re.sub(r"\.(html|md)$", "", path)

    # Strip trailing slash
    path = path.rstrip("/")

    return path if path else None


def _top_folder(path: str) -> str:
    """Return the top-level folder: ``guide``, ``api``, ``tutorial``, etc."""
    return path.split("/")[0] if "/" in path or path else path


def _sub_folder(path: str) -> str:
    """Return the first two path segments: ``guide/essentials``, ``api``, etc."""
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else parts[0]


def _classify_ref_type(source_file: str, target_path: str) -> CrossRefType:
    """Classify a cross-reference by source and target folder paths."""
    src_top = _top_folder(source_file)
    tgt_top = _top_folder(target_path)

    # guide ↔ api is HIGH value
    if {src_top, tgt_top} == {"guide", "api"}:
        return CrossRefType.HIGH

    # Same subfolder is MEDIUM
    src_sub = _sub_folder(source_file)
    tgt_sub = _sub_folder(target_path)
    if src_sub == tgt_sub:
        return CrossRefType.MEDIUM

    # Everything else is LOW
    return CrossRefType.LOW


def extract_cross_references(chunk: Chunk) -> list[CrossReference]:
    """Extract all internal cross-references from a chunk's content.

    Returns a list of :class:`CrossReference` objects with resolved paths
    and classified importance.
    """
    refs: list[CrossReference] = []
    seen_targets: set[str] = set()

    for m in _LINK_RE.finditer(chunk.content):
        link_text = m.group(1)
        raw_link = m.group(2)

        target = _resolve_target_path(raw_link, chunk.metadata.file_path)
        if target is None:
            continue

        # Deduplicate within the same chunk
        if target in seen_targets:
            continue
        seen_targets.add(target)

        ref_type = _classify_ref_type(chunk.metadata.file_path, target)
        refs.append(
            CrossReference(
                source_chunk_id=chunk.chunk_id,
                target_path=target,
                link_text=link_text,
                ref_type=ref_type,
            )
        )

    return refs


def build_crossref_graph(
    chunks: list[Chunk],
) -> dict[str, list[CrossReference]]:
    """Build the full cross-reference graph from all chunks.

    Returns a dict mapping each chunk_id to its outgoing cross-references.
    Also updates each chunk's ``metadata.cross_references`` with target paths.
    """
    graph: dict[str, list[CrossReference]] = {}

    for chunk in chunks:
        refs = extract_cross_references(chunk)
        if refs:
            graph[chunk.chunk_id] = refs
            chunk.metadata.cross_references = [r.target_path for r in refs]

    return graph
