"""Reciprocal Rank Fusion (RRF) implementation for multi-query fusion.

When multiple query variants (original, rewrites, sub-questions, step-back)
each produce their own ranked list of search hits, RRF combines them into
a single ranking that rewards chunks appearing across multiple result sets.
"""

from vue_docs_core.clients.qdrant import SearchHit

# Standard RRF constant (from the original paper)
RRF_K = 60


def reciprocal_rank_fusion(
    result_sets: list[list[SearchHit]],
    *,
    k: int = RRF_K,
) -> list[SearchHit]:
    """Fuse multiple ranked result sets into a single ranking using RRF.

    For each chunk, computes: score = sum(1 / (k + rank_i)) across all
    result sets where the chunk appears. Higher scores indicate chunks
    that rank well across multiple queries.

    Deduplicates by chunk_id, keeping the payload from the highest-scoring
    occurrence.
    """
    if not result_sets:
        return []

    if len(result_sets) == 1:
        return result_sets[0]

    # Accumulate RRF scores per chunk_id
    rrf_scores: dict[str, float] = {}
    best_payload: dict[str, dict] = {}

    for result_set in result_sets:
        for rank, hit in enumerate(result_set):
            chunk_id = hit.chunk_id
            rrf_score = 1.0 / (k + rank + 1)  # rank is 0-indexed, RRF uses 1-indexed
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + rrf_score

            # Keep payload from the occurrence with the highest original score
            if chunk_id not in best_payload or hit.score > best_payload[chunk_id].get(
                "_best_score", 0
            ):
                best_payload[chunk_id] = hit.payload
                best_payload[chunk_id]["_best_score"] = hit.score

    # Build fused results sorted by RRF score
    fused: list[SearchHit] = []
    for chunk_id, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
        payload = best_payload[chunk_id]
        payload.pop("_best_score", None)
        fused.append(
            SearchHit(
                chunk_id=chunk_id,
                score=score,
                payload=payload,
            )
        )

    return fused
