"""Qdrant upsert orchestration (chunks, HyPE points, summaries)."""

import logging

from qdrant_client.models import SparseVector

from vue_docs_core.clients.qdrant import QdrantDocClient
from vue_docs_core.models.chunk import Chunk

logger = logging.getLogger(__name__)


def _chunk_payload(chunk: Chunk) -> dict:
    """Build the Qdrant payload dict from a chunk."""
    m = chunk.metadata
    return {
        "file_path": m.file_path,
        "folder_path": m.folder_path,
        "page_title": m.page_title,
        "section_title": m.section_title,
        "subsection_title": m.subsection_title,
        "breadcrumb": m.breadcrumb,
        "global_sort_key": m.global_sort_key,
        "chunk_type": chunk.chunk_type.value,
        "content_type": m.content_type,
        "language_tag": m.language_tag,
        "api_style": m.api_style,
        "api_entities": m.api_entities,
        "cross_references": m.cross_references,
        "parent_chunk_id": m.parent_chunk_id,
        "sibling_chunk_ids": m.sibling_chunk_ids,
        "child_chunk_ids": m.child_chunk_ids,
        "preceding_prose": m.preceding_prose,
        "content": chunk.content,
        "content_hash": chunk.content_hash,
    }


def upsert_chunks_batch(
    chunks: list[Chunk],
    dense_vectors: list[list[float]],
    sparse_vectors: list[SparseVector],
    qdrant: QdrantDocClient,
) -> None:
    """Upsert a batch of chunks with their vectors into Qdrant."""
    if not chunks:
        return

    chunk_ids = [c.chunk_id for c in chunks]
    payloads = [_chunk_payload(c) for c in chunks]

    qdrant.upsert_chunks(
        chunk_ids=chunk_ids,
        dense_vectors=dense_vectors,
        sparse_vectors=sparse_vectors,
        payloads=payloads,
    )
    logger.info("Upserted %d chunks to Qdrant", len(chunks))
