"""Cross-reference expansion logic.

For top-ranked search results, follow outgoing cross-references to pull in
related chunks that the user didn't directly search for. This is especially
valuable for multi-hop questions where the answer spans multiple doc pages.

Expansion rules by cross-reference priority:
  HIGH  (guide <-> api): always follow, for all expanded hits
  MEDIUM (same-folder):  follow for top-10 candidates only
  LOW   (cross-folder):  follow for top-5 candidates only

Only one hop is followed — cross-references of expanded chunks are not expanded.
"""

import logging

from vue_docs_core.clients.qdrant import QdrantDocClient, SearchHit
from vue_docs_core.models.crossref import CrossRefType

logger = logging.getLogger(__name__)

# Score assigned to expanded chunks (below any real retrieval score,
# so they don't outrank directly-matched results before reranking).
_EXPANSION_SCORE = 0.0

# How many top hits to consider for MEDIUM-priority expansion.
_MEDIUM_CUTOFF = 10

# How many top hits to consider for LOW-priority expansion.
_LOW_CUTOFF = 5

# Maximum number of target pages to expand (limits Qdrant fetch size).
_MAX_TARGET_PAGES = 5


def expand_cross_references(
    hits: list[SearchHit],
    qdrant: QdrantDocClient,
    crossref_types: dict[str, dict[str, str]] | None = None,
) -> list[SearchHit]:
    """Expand search results by following cross-references.

    For each hit's outgoing cross-references (stored as target paths in
    the payload), fetch the referenced chunks from Qdrant and merge them
    into the result set. Deduplicates by chunk_id.

    Args:
        hits: Candidate hits sorted by score descending.
        qdrant: Qdrant client for fetching expanded chunks.
        crossref_types: Optional mapping of source_chunk_id -> {target_path: ref_type}.
            If not provided, all cross-references are treated as HIGH priority.

    Returns:
        Expanded hit list with new chunks appended, deduplicated.
    """
    if not hits:
        return hits

    # Collect existing chunk IDs to avoid duplicates
    seen_ids: set[str] = {h.chunk_id for h in hits}

    # Collect target paths to expand, respecting priority cutoffs.
    # Track by priority so we can cap to _MAX_TARGET_PAGES, keeping HIGH first.
    _PRIORITY_ORDER = {CrossRefType.HIGH: 0, CrossRefType.MEDIUM: 1, CrossRefType.LOW: 2}
    targets: dict[str, int] = {}  # file_path -> best priority (lower = higher)

    for rank, hit in enumerate(hits):
        xrefs = hit.payload.get("cross_references", [])
        if not xrefs:
            continue

        for target_path in xrefs:
            ref_type = _get_ref_type(hit.chunk_id, target_path, crossref_types)

            # Apply priority cutoffs
            if ref_type == CrossRefType.LOW and rank >= _LOW_CUTOFF:
                continue
            if ref_type == CrossRefType.MEDIUM and rank >= _MEDIUM_CUTOFF:
                continue

            file_path = target_path if target_path.endswith(".md") else f"{target_path}.md"
            prio = _PRIORITY_ORDER[ref_type]
            if file_path not in targets or prio < targets[file_path]:
                targets[file_path] = prio

    if not targets:
        return hits

    # Cap to _MAX_TARGET_PAGES, keeping highest-priority targets first
    sorted_targets = sorted(targets.items(), key=lambda kv: kv[1])
    target_paths = [fp for fp, _ in sorted_targets[:_MAX_TARGET_PAGES]]

    # Fetch section-level chunks for the target pages
    payloads = qdrant.get_by_file_paths(
        file_paths=target_paths,
        chunk_types=["section", "subsection"],
    )

    # Add expanded chunks that aren't already in results
    expanded_count = 0
    for payload in payloads:
        chunk_id = payload.get("chunk_id", "")
        if not chunk_id or chunk_id in seen_ids:
            continue

        hits.append(SearchHit(
            chunk_id=chunk_id,
            score=_EXPANSION_SCORE,
            payload=payload,
        ))
        seen_ids.add(chunk_id)
        expanded_count += 1

    if expanded_count:
        logger.info(
            "Expanded %d cross-ref targets → %d new chunks",
            len(target_paths), expanded_count,
        )

    return hits


def _get_ref_type(
    source_chunk_id: str,
    target_path: str,
    crossref_types: dict[str, dict[str, str]] | None,
) -> CrossRefType:
    """Look up the cross-reference type, defaulting to HIGH if unknown."""
    if crossref_types is None:
        return CrossRefType.HIGH

    source_refs = crossref_types.get(source_chunk_id, {})
    type_str = source_refs.get(target_path, "")
    try:
        return CrossRefType(type_str)
    except ValueError:
        return CrossRefType.HIGH
