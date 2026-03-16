"""Cross-reference expansion logic.

For top-ranked search results, follow outgoing cross-references to pull in
related chunks that the user didn't directly search for. This is especially
valuable for multi-hop questions where the answer spans multiple doc pages.

Cross-references can be:
  - Targeted: "guide/components/v-model#basic-usage" → fetch that specific chunk
  - Page-level: "guide/essentials/forms" → fetch all sections from that page

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

# Maximum number of cross-reference targets to expand.
_MAX_TARGETS = 10


def expand_cross_references(
    hits: list[SearchHit],
    qdrant: QdrantDocClient,
    crossref_types: dict[str, dict[str, str]] | None = None,
) -> list[SearchHit]:
    """Expand search results by following cross-references.

    For each hit's outgoing cross-references, fetch the referenced chunks
    from Qdrant and merge them into the result set. Targeted references
    (with anchors) fetch a single chunk; page-level references fetch all
    sections from that page.

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

    # Collect targets to expand, separated into targeted (with anchor) and page-level.
    _PRIORITY_ORDER = {CrossRefType.HIGH: 0, CrossRefType.MEDIUM: 1, CrossRefType.LOW: 2}
    # targeted_ids: chunk_id (path#anchor) -> best priority
    targeted_ids: dict[str, int] = {}
    # page_paths: file_path -> best priority (for refs without anchors)
    page_paths: dict[str, int] = {}

    for rank, hit in enumerate(hits):
        xrefs = hit.payload.get("cross_references", [])
        if not xrefs:
            continue

        for target in xrefs:
            ref_type = _get_ref_type(hit.chunk_id, target, crossref_types)

            # Apply priority cutoffs
            if ref_type == CrossRefType.LOW and rank >= _LOW_CUTOFF:
                continue
            if ref_type == CrossRefType.MEDIUM and rank >= _MEDIUM_CUTOFF:
                continue

            prio = _PRIORITY_ORDER[ref_type]

            if "#" in target:
                # Targeted reference — fetch specific chunk by ID
                # Target is already in chunk_id format: "path/to/page#section-slug"
                if target not in targeted_ids or prio < targeted_ids[target]:
                    targeted_ids[target] = prio
            else:
                # Page-level reference — fetch all sections
                file_path = target if target.endswith(".md") else f"{target}.md"
                if file_path not in page_paths or prio < page_paths[file_path]:
                    page_paths[file_path] = prio

    if not targeted_ids and not page_paths:
        return hits

    # Cap total targets, prioritizing targeted (specific) over page-level
    all_targets = (
        [(tid, prio, "targeted") for tid, prio in targeted_ids.items()]
        + [(fp, prio, "page") for fp, prio in page_paths.items()]
    )
    all_targets.sort(key=lambda t: (t[1], 0 if t[2] == "targeted" else 1))
    selected = all_targets[:_MAX_TARGETS]

    final_chunk_ids = [t[0] for t in selected if t[2] == "targeted"]
    final_page_paths = [t[0] for t in selected if t[2] == "page"]

    # Fetch targeted chunks by chunk_id
    expanded_count = 0
    if final_chunk_ids:
        payloads = qdrant.get_by_chunk_ids(final_chunk_ids)
        for payload in payloads:
            chunk_id = payload.get("chunk_id", "")
            if chunk_id and chunk_id not in seen_ids:
                hits.append(SearchHit(
                    chunk_id=chunk_id,
                    score=_EXPANSION_SCORE,
                    payload=payload,
                ))
                seen_ids.add(chunk_id)
                expanded_count += 1

    # Fetch page-level chunks by file_path
    if final_page_paths:
        payloads = qdrant.get_by_file_paths(
            file_paths=final_page_paths,
            chunk_types=["section", "subsection"],
        )
        for payload in payloads:
            chunk_id = payload.get("chunk_id", "")
            if chunk_id and chunk_id not in seen_ids:
                hits.append(SearchHit(
                    chunk_id=chunk_id,
                    score=_EXPANSION_SCORE,
                    payload=payload,
                ))
                seen_ids.add(chunk_id)
                expanded_count += 1

    if expanded_count:
        logger.info(
            "Expanded %d targeted + %d page-level refs → %d new chunks",
            len(final_chunk_ids), len(final_page_paths), expanded_count,
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
