"""vue_docs_search tool implementation."""

import logging

from vue_docs_core.clients.jina import JinaClient, TASK_RETRIEVAL_QUERY
from vue_docs_core.retrieval.reconstruction import reconstruct_results

from vue_docs_server.startup import state

logger = logging.getLogger(__name__)


# Number of candidates to retrieve from Qdrant per prefetch arm.
# This should be large enough to give the reranker a good candidate pool.
_RETRIEVAL_LIMIT = 50


async def vue_docs_search(
    query: str,
    scope: str = "all",
    max_results: int = 3,
) -> str:
    """Search the Vue.js documentation.

    Performs hybrid dense+sparse search over the indexed Vue documentation,
    returning reconstructed, readable documentation fragments ordered by
    the documentation's natural reading flow.

    Args:
        query: The search query — a developer question or topic.
        scope: Documentation scope to search within. Use "all" for everything,
               or a folder path like "guide", "guide/essentials", "api",
               "tutorial", "examples" to narrow the search.
        max_results: Maximum number of documentation sections to return (1-20).

    Returns:
        Formatted documentation fragments with breadcrumbs, code examples,
        and source URLs.
    """
    if not state.is_ready:
        return "Error: Server not initialized. Please try again shortly."

    max_results = max(1, min(20, max_results))

    # Embed the query
    jina = JinaClient()
    try:
        embed_result = await jina.embed([query], task=TASK_RETRIEVAL_QUERY)
        if not embed_result.embeddings:
            return "Error: Failed to generate query embedding."
        dense_vector = embed_result.embeddings[0]
    finally:
        await jina.close()

    # Generate BM25 sparse vector
    sparse_vector = state.bm25.get_query_sparse_vector(query)

    # Detect API entities in query for boosting
    entity_boost = _detect_entities(query)

    # Run hybrid search — retrieve a wide candidate pool for reranking
    scope_filter = scope if scope != "all" else None
    hits = state.qdrant.hybrid_search(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        limit=_RETRIEVAL_LIMIT,
        scope_filter=scope_filter,
        entity_boost=entity_boost if entity_boost else None,
    )

    if not hits:
        # Retry with broader scope if scoped search yielded nothing
        if scope_filter:
            logger.info("No results for scope '%s', retrying with all", scope)
            hits = state.qdrant.hybrid_search(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                limit=_RETRIEVAL_LIMIT,
                entity_boost=entity_boost if entity_boost else None,
            )

    if not hits:
        return f"No documentation found for: {query}"

    # Resolve HyPE question hits to their parent chunks
    hits = _resolve_hype_hits(hits)

    return reconstruct_results(hits, max_results=max_results)


def _resolve_hype_hits(hits: list) -> list:
    """Replace HyPE question hits with their parent chunks.

    When a HyPE question point matches a query, we resolve it to the
    parent chunk for inclusion in results. Deduplicates by chunk_id,
    keeping the highest score.
    """
    from vue_docs_core.clients.qdrant import SearchHit

    resolved: list[SearchHit] = []
    seen_chunk_ids: dict[str, float] = {}
    parent_ids_to_fetch: list[str] = []
    hype_scores: dict[str, float] = {}

    for hit in hits:
        if hit.payload.get("chunk_type") == "hype_question":
            parent_id = hit.payload.get("parent_chunk_id", "")
            if parent_id and parent_id not in seen_chunk_ids:
                parent_ids_to_fetch.append(parent_id)
                hype_scores[parent_id] = hit.score
            elif parent_id in seen_chunk_ids:
                # Keep the highest score
                seen_chunk_ids[parent_id] = max(seen_chunk_ids[parent_id], hit.score)
        else:
            chunk_id = hit.chunk_id
            if chunk_id not in seen_chunk_ids or hit.score > seen_chunk_ids[chunk_id]:
                seen_chunk_ids[chunk_id] = hit.score
                resolved.append(hit)

    # Fetch parent chunks for HyPE hits
    if parent_ids_to_fetch and state.qdrant:
        parent_payloads = state.qdrant.get_by_chunk_ids(parent_ids_to_fetch)
        for payload in parent_payloads:
            parent_id = payload.get("chunk_id", "")
            if parent_id and parent_id not in seen_chunk_ids:
                score = hype_scores.get(parent_id, 0.0)
                resolved.append(SearchHit(
                    chunk_id=parent_id,
                    score=score,
                    payload=payload,
                ))
                seen_chunk_ids[parent_id] = score

    # Re-sort by score descending
    resolved.sort(key=lambda h: h.score, reverse=True)
    return resolved


def _detect_entities(query: str) -> list[str]:
    """Detect API entity names in the query using the EntityMatcher.

    Uses dictionary matching, bigram matching, synonym lookup, and
    fuzzy matching (rapidfuzz) for typo tolerance.
    """
    if state.entity_matcher is None:
        return []
    match_result = state.entity_matcher.match(query)
    return match_result.entities
