"""vue_docs_search tool implementation."""

import logging
from typing import Annotated

from fastmcp.exceptions import ToolError
from pydantic import Field

from vue_docs_core.clients.jina import JinaClient, TASK_RETRIEVAL_QUERY
from vue_docs_core.clients.qdrant import SearchHit
from vue_docs_core.retrieval.expansion import expand_cross_references
from vue_docs_core.retrieval.reconstruction import reconstruct_results

from vue_docs_server.startup import state

logger = logging.getLogger(__name__)


# Number of candidates to retrieve from Qdrant per prefetch arm.
_RETRIEVAL_LIMIT = 50

# Minimum reranker relevance score to include a result.
_RERANK_MIN_SCORE = 0.01


async def vue_docs_search(
    query: Annotated[str, Field(
        description="A developer question or topic about Vue.js. "
                    "Examples: 'how does computed caching work', "
                    "'v-model on custom components', "
                    "'defineProps TypeScript usage'."
    )],
    scope: Annotated[str, Field(
        default="all",
        description="Documentation section to search within. Use 'all' for the "
                    "full docs, or narrow with a folder path like 'guide', "
                    "'guide/essentials', 'guide/components', 'api', 'tutorial'. "
                    "Read the vue://scopes resource for the complete list."
    )] = "all",
    max_results: Annotated[int, Field(
        default=3,
        ge=1,
        le=20,
        description="Number of documentation sections to return."
    )] = 3,
) -> str:
    """Search the Vue.js documentation.

    Performs hybrid semantic + keyword search over the indexed Vue documentation,
    reranks candidates, and returns reconstructed, readable documentation
    fragments ordered by the documentation's natural reading flow.
    """
    if not state.is_ready:
        raise ToolError("Server not initialized. Please try again shortly.")

    jina = JinaClient()
    try:
        # Embed the query
        embed_result = await jina.embed([query], task=TASK_RETRIEVAL_QUERY)
        if not embed_result.embeddings:
            return "Error: Failed to generate query embedding."
        dense_vector = embed_result.embeddings[0]

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

        # Expand results via cross-references (before reranking)
        hits = expand_cross_references(hits, state.qdrant)

        # Rerank candidates with Jina reranker v3
        hits = await _rerank_hits(jina, query, hits)
    finally:
        await jina.close()

    # Discard low-relevance results after reranking
    hits = [h for h in hits if h.score >= _RERANK_MIN_SCORE]

    if not hits:
        return f"No documentation found for: {query}"

    return reconstruct_results(hits, max_results=max_results)


async def _rerank_hits(
    jina: JinaClient,
    query: str,
    hits: list[SearchHit],
) -> list[SearchHit]:
    """Rerank candidate hits using Jina reranker v3.

    Sends all candidates through the listwise reranker and returns hits
    reordered by reranker relevance. Falls back to the original ordering
    on failure.

    Args:
        jina: Active JinaClient instance.
        query: The original search query.
        hits: Candidate hits after HyPE resolution, sorted by fusion score.

    Returns:
        Reranked hits.
    """
    if not hits:
        return hits

    # Build document texts for the reranker — use content with breadcrumb context
    documents = []
    for hit in hits:
        payload = hit.payload
        breadcrumb = payload.get("breadcrumb", "")
        content = payload.get("content", "")
        preceding_prose = payload.get("preceding_prose", "")

        # For code blocks, include the preceding prose for context
        if payload.get("chunk_type") == "code_block" and preceding_prose:
            doc_text = f"{breadcrumb}\n{preceding_prose}\n{content}"
        elif breadcrumb:
            doc_text = f"{breadcrumb}\n{content}"
        else:
            doc_text = content
        documents.append(doc_text)

    try:
        result = await jina.rerank(query=query, documents=documents)

        # Rebuild hits list in reranked order with reranker scores
        reranked: list[SearchHit] = []
        for idx, score in zip(result.indices, result.scores):
            hit = hits[idx]
            reranked.append(SearchHit(
                chunk_id=hit.chunk_id,
                score=score,
                payload=hit.payload,
            ))

        logger.info(
            "Reranked %d candidates (tokens: %d)",
            len(hits), result.total_tokens,
        )
        return reranked

    except Exception:
        logger.warning("Reranking failed, falling back to fusion scores", exc_info=True)
        return hits


def _resolve_hype_hits(hits: list) -> list:
    """Replace HyPE question hits with their parent chunks.

    When a HyPE question point matches a query, we resolve it to the
    parent chunk for inclusion in results. Deduplicates by chunk_id,
    keeping the highest score.
    """
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
