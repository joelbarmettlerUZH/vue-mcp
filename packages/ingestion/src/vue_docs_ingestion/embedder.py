"""Batch dense embedding via Jina AI."""

import logging

from vue_docs_core.clients.jina import TASK_RETRIEVAL_PASSAGE, JinaClient
from vue_docs_core.models.chunk import Chunk

logger = logging.getLogger(__name__)


async def embed_dense_batched(
    chunks: list[Chunk],
    jina_client: JinaClient,
    batch_size: int = 64,
) -> tuple[list[list[float]], int]:
    """Embed chunks with Jina dense vectors.

    Args:
        chunks: Chunks to embed.
        jina_client: Initialized Jina client.
        batch_size: Max texts per Jina API call.

    Returns:
        Tuple of (dense_vectors, total_tokens).
    """
    if not chunks:
        return [], 0

    texts = [chunk.content for chunk in chunks]
    result = await jina_client.embed_batched(texts, task=TASK_RETRIEVAL_PASSAGE, batch_size=batch_size)
    logger.info(
        "Jina embedding: %d chunks, %d tokens used",
        len(chunks), result.total_tokens,
    )
    return result.embeddings, result.total_tokens
