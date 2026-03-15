"""Dense embedding via Jina AI."""

import logging

from vue_docs_core.clients.jina import TASK_RETRIEVAL_PASSAGE, JinaClient
from vue_docs_core.models.chunk import Chunk

logger = logging.getLogger(__name__)


async def embed_dense(
    chunks: list[Chunk],
    jina_client: JinaClient,
) -> tuple[list[list[float]], int]:
    """Embed chunks with Jina dense vectors in a single API call.

    Jina imposes no per-batch item limit, so we send the entire corpus in one
    request to minimise round-trips and reduce timeout risk.

    Args:
        chunks: Chunks to embed.
        jina_client: Initialized Jina client.

    Returns:
        Tuple of (dense_vectors, total_tokens).
    """
    if not chunks:
        return [], 0

    texts = [chunk.content for chunk in chunks]
    result = await jina_client.embed(texts, task=TASK_RETRIEVAL_PASSAGE)
    logger.info(
        "Jina embedding: %d chunks, %d tokens used",
        len(chunks), result.total_tokens,
    )
    return result.embeddings, result.total_tokens
