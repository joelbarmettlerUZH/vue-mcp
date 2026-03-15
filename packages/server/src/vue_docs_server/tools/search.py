"""vue_docs_search tool implementation."""

import asyncio
import logging

from vue_docs_core.clients.jina import JinaClient, TASK_RETRIEVAL_QUERY
from vue_docs_core.retrieval.reconstruction import reconstruct_results

from vue_docs_server.startup import state

logger = logging.getLogger(__name__)


async def vue_docs_search(
    query: str,
    scope: str = "all",
    max_results: int = 10,
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

    # Run hybrid search
    scope_filter = scope if scope != "all" else None
    hits = state.qdrant.hybrid_search(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        limit=max_results * 3,  # Fetch extra for filtering
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
                limit=max_results * 3,
                entity_boost=entity_boost if entity_boost else None,
            )

    if not hits:
        return f"No documentation found for: {query}"

    return reconstruct_results(hits, max_results=max_results)


def _detect_entities(query: str) -> list[str]:
    """Detect API entity names in the query using dictionary + synonym matching.

    This is a lightweight, deterministic extraction — no LLM needed.
    """
    detected: set[str] = set()
    query_lower = query.lower().strip()

    # Normalize: strip backticks
    query_clean = query_lower.replace("`", "")

    # Check against entity dictionary
    for entity_name in state.entity_index.entities:
        name_lower = entity_name.lower()
        if name_lower in query_clean:
            detected.add(entity_name)

    # Check synonym table
    for phrase, api_names in state.synonym_table.items():
        if phrase.lower() in query_clean:
            detected.update(api_names)

    return list(detected)
