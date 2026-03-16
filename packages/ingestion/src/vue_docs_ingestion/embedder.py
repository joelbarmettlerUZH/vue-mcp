"""Dense embedding via Jina AI."""

import logging

from vue_docs_core.clients.jina import TASK_RETRIEVAL_PASSAGE, JinaClient
from vue_docs_core.models.chunk import Chunk

logger = logging.getLogger(__name__)

# Batch size for Jina embedding requests. With contextual prefixes the
# per-chunk payload is larger, so we batch to avoid Cloudflare timeouts.
_EMBED_BATCH_SIZE = 256


async def embed_dense(
    chunks: list[Chunk],
    jina_client: JinaClient,
) -> tuple[list[list[float]], int]:
    """Embed chunks with Jina dense vectors in batches.

    Args:
        chunks: Chunks to embed.
        jina_client: Initialized Jina client.

    Returns:
        Tuple of (dense_vectors, total_tokens).
    """
    if not chunks:
        return [], 0

    # Prepend contextual prefix to content before embedding (Anthropic's
    # contextual retrieval technique). The prefix situates the chunk within
    # its page, improving semantic search quality. The prefix is stored
    # separately in the payload so it can be stripped for display.
    texts = []
    for chunk in chunks:
        if chunk.contextual_prefix:
            texts.append(f"{chunk.contextual_prefix}\n\n{chunk.content}")
        else:
            texts.append(chunk.content)

    result = await jina_client.embed_batched(
        texts, task=TASK_RETRIEVAL_PASSAGE, batch_size=_EMBED_BATCH_SIZE
    )
    logger.info(
        "Jina embedding: %d chunks, %d tokens used",
        len(chunks), result.total_tokens,
    )
    return result.embeddings, result.total_tokens
