"""vue_docs_search tool implementation."""

from typing import Annotated

from fastmcp import Context
from fastmcp.exceptions import ToolError
from fastmcp.telemetry import get_tracer
from pydantic import Field

from vue_docs_core.clients.jina import JinaClient
from vue_docs_core.clients.qdrant import SearchHit
from vue_docs_core.config import RERANK_MIN_SCORE, RETRIEVAL_LIMIT, TASK_RETRIEVAL_QUERY
from vue_docs_core.retrieval.expansion import expand_cross_references
from vue_docs_core.retrieval.reconstruction import reconstruct_results
from vue_docs_server.startup import state

TOTAL_STEPS = 6
_tracer = get_tracer()


async def vue_docs_search(
    query: Annotated[
        str,
        Field(
            max_length=2000,
            description="A developer question or topic about Vue.js. "
            "Examples: 'how does computed caching work', "
            "'v-model on custom components', "
            "'defineProps TypeScript usage'.",
        ),
    ],
    scope: Annotated[
        str,
        Field(
            default="all",
            description="Documentation section to search within. Use 'all' for the "
            "full docs, or narrow with a folder path like 'guide', "
            "'guide/essentials', 'guide/components', 'api', 'tutorial'. "
            "Read the vue://scopes resource for the complete list.",
        ),
    ] = "all",
    max_results: Annotated[
        int,
        Field(default=3, ge=1, le=20, description="Number of documentation sections to return."),
    ] = 3,
    ctx: Context = None,
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
        # Step 1: Embed the query
        await ctx.report_progress(1, TOTAL_STEPS)
        await ctx.info(f"Embedding query: {query!r}")
        with _tracer.start_as_current_span("embed_query") as span:
            span.set_attribute("query.length", len(query))
            embed_result = await jina.embed([query], task=TASK_RETRIEVAL_QUERY)
            if not embed_result.embeddings:
                return "Error: Failed to generate query embedding."
            dense_vector = embed_result.embeddings[0]

            # Generate BM25 sparse vector
            sparse_vector = state.bm25.get_query_sparse_vector(query)

        # Step 2: Run hybrid search (no entity filter — BM25 covers keyword matching)
        await ctx.report_progress(2, TOTAL_STEPS)
        await ctx.info("Searching documentation")
        with _tracer.start_as_current_span("hybrid_search") as span:
            span.set_attribute("search.scope", scope)
            scope_filter = scope if scope != "all" else None
            hits = state.qdrant.hybrid_search(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                limit=RETRIEVAL_LIMIT,
                scope_filter=scope_filter,
            )

            if not hits and scope_filter:
                await ctx.warning(f"No results in scope '{scope}', expanding to all documentation")
                span.set_attribute("search.scope_fallback", True)
                hits = state.qdrant.hybrid_search(
                    dense_vector=dense_vector,
                    sparse_vector=sparse_vector,
                    limit=RETRIEVAL_LIMIT,
                )

            span.set_attribute("search.hit_count", len(hits))

        if not hits:
            return f"No documentation found for: {query}"

        # Step 3: Resolve HyPE question hits to their parent chunks
        await ctx.report_progress(3, TOTAL_STEPS)
        await ctx.info("Resolving related content")
        with _tracer.start_as_current_span("resolve_hype"):
            hits = _resolve_hype_hits(hits)

        # Step 4: Expand results via cross-references (before reranking)
        await ctx.report_progress(4, TOTAL_STEPS)
        await ctx.info("Expanding cross-references")
        with _tracer.start_as_current_span("expand_crossrefs") as span:
            pre_count = len(hits)
            hits = expand_cross_references(hits, state.qdrant)
            span.set_attribute("crossref.added", len(hits) - pre_count)

        # Step 5: Rerank candidates with Jina reranker v3
        await ctx.report_progress(5, TOTAL_STEPS)
        await ctx.info("Reranking candidates")
        with _tracer.start_as_current_span("rerank") as span:
            span.set_attribute("rerank.candidate_count", len(hits))
            hits = await _rerank_hits(jina, query, hits, ctx)
    finally:
        await jina.close()

    # Discard low-relevance results after reranking
    hits = [h for h in hits if h.score >= RERANK_MIN_SCORE]

    if not hits:
        return f"No documentation found for: {query}"

    # Step 6: Reconstruct results
    await ctx.report_progress(6, TOTAL_STEPS)
    await ctx.info("Reconstructing results")

    # Track query in session history
    history = await ctx.get_state("query_history") or []
    history.append({"query": query, "scope": scope, "results": len(hits)})
    await ctx.set_state("query_history", history[-10:])

    return reconstruct_results(hits, max_results=max_results)


async def _rerank_hits(
    jina: JinaClient,
    query: str,
    hits: list[SearchHit],
    ctx: Context,
) -> list[SearchHit]:
    """Rerank candidate hits using Jina reranker v3.

    Sends all candidates through the listwise reranker and returns hits
    reordered by reranker relevance. Falls back to the original ordering
    on failure.
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
        for idx, score in zip(result.indices, result.scores, strict=False):
            hit = hits[idx]
            reranked.append(
                SearchHit(
                    chunk_id=hit.chunk_id,
                    score=score,
                    payload=hit.payload,
                )
            )

        await ctx.info(f"Reranked {len(hits)} candidates (tokens: {result.total_tokens})")
        return reranked

    except Exception:
        await ctx.warning("Reranking failed, falling back to fusion scores")
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
                resolved.append(
                    SearchHit(
                        chunk_id=parent_id,
                        score=score,
                        payload=payload,
                    )
                )
                seen_chunk_ids[parent_id] = score

    # Re-sort by score descending
    resolved.sort(key=lambda h: h.score, reverse=True)
    return resolved
