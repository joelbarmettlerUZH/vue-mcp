"""Dense embedding via Jina AI."""

import logging
from typing import Annotated

from pydantic import BaseModel, Field

from vue_docs_core.clients.jina import JinaClient
from vue_docs_core.config import EMBED_BATCH_SIZE, TASK_RETRIEVAL_PASSAGE, TASK_RETRIEVAL_QUERY
from vue_docs_core.models.chunk import Chunk

logger = logging.getLogger(__name__)


class HypeEmbedding(BaseModel):
    """A single HyPE question embedding with its parent chunk reference."""

    model_config = {"arbitrary_types_allowed": True}

    question: Annotated[str, Field(description="The hypothetical developer question text")]
    parent_chunk_id: Annotated[
        str, Field(description="Chunk ID of the parent chunk this question was generated from")
    ]
    parent_chunk: Annotated[Chunk, Field(description="The parent chunk Pydantic model instance")]
    embedding: Annotated[list[float], Field(description="Dense embedding vector for this question")]


class EmbedResult(BaseModel):
    """Result of a dense embedding pass."""

    vectors: Annotated[list[list[float]], Field(description="List of dense embedding vectors")]
    total_tokens: Annotated[
        int, Field(description="Total tokens consumed by the embedding request")
    ]


class HypeEmbedResult(BaseModel):
    """Result of embedding HyPE questions."""

    embeddings: Annotated[
        list[HypeEmbedding],
        Field(description="List of HyPE question embeddings with parent references"),
    ]
    total_tokens: Annotated[
        int, Field(description="Total tokens consumed by the HyPE embedding request")
    ]

    model_config = {"arbitrary_types_allowed": True}


async def embed_dense(
    chunks: list[Chunk],
    jina_client: JinaClient,
) -> EmbedResult:
    """Embed chunks with Jina dense vectors in batches."""
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
        texts, task=TASK_RETRIEVAL_PASSAGE, batch_size=EMBED_BATCH_SIZE
    )
    logger.info(
        "Jina embedding: %d chunks, %d tokens used",
        len(chunks),
        result.total_tokens,
    )
    return EmbedResult(vectors=result.embeddings, total_tokens=result.total_tokens)


async def embed_hype_questions(
    chunks: list[Chunk],
    jina_client: JinaClient,
) -> HypeEmbedResult:
    """Embed HyPE questions from chunks using query-side task type.

    HyPE questions are embedded with TASK_RETRIEVAL_QUERY because they
    represent the kinds of queries users would ask, not document passages.
    """
    # Collect all questions with their parent references
    questions: list[str] = []
    parent_refs: list[tuple[str, Chunk]] = []

    for chunk in chunks:
        for question in chunk.hype_questions:
            questions.append(question)
            parent_refs.append((chunk.chunk_id, chunk))

    result = await jina_client.embed_batched(
        questions, task=TASK_RETRIEVAL_QUERY, batch_size=EMBED_BATCH_SIZE
    )

    hype_embeddings = []
    for i, embedding in enumerate(result.embeddings):
        parent_id, parent_chunk = parent_refs[i]
        hype_embeddings.append(
            HypeEmbedding(
                question=questions[i],
                parent_chunk_id=parent_id,
                parent_chunk=parent_chunk,
                embedding=embedding,
            )
        )

    logger.info(
        "Jina HyPE embedding: %d questions from %d chunks, %d tokens used",
        len(questions),
        sum(1 for c in chunks if c.hype_questions),
        result.total_tokens,
    )
    return HypeEmbedResult(embeddings=hype_embeddings, total_tokens=result.total_tokens)
