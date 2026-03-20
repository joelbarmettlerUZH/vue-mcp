"""Qdrant collection setup, upsert, and hybrid search."""

import logging
from typing import Annotated

from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import (
    BinaryQuantization,
    BinaryQuantizationConfig,
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    NearestQuery,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from vue_docs_core.config import DENSE_VECTOR_NAME, INDEXED_FIELDS, SPARSE_VECTOR_NAME, settings

logger = logging.getLogger(__name__)


class SearchHit(BaseModel):
    chunk_id: Annotated[str, Field(description="Unique identifier of the matched chunk")]
    score: Annotated[float, Field(description="Relevance score from the search")]
    payload: Annotated[dict, Field(description="Full payload data of the matched point")]


class QdrantDocClient:
    """Client for Vue docs Qdrant collection."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str | None = None,
        dense_dim: int = 1024,
    ):
        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key
        self.collection = collection or settings.qdrant_collection
        self.dense_dim = dense_dim
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            kwargs: dict = {"url": self.url}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            self._client = QdrantClient(**kwargs)
        return self._client

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def setup_collection(self, recreate: bool = False):
        """Create the collection with dense + sparse vectors and payload indices."""
        exists = self.client.collection_exists(self.collection)

        if exists and recreate:
            logger.info("Deleting existing collection '%s'", self.collection)
            self.client.delete_collection(self.collection)
            exists = False

        if not exists:
            logger.info(
                "Creating collection '%s' (dense_dim=%d)",
                self.collection,
                self.dense_dim,
            )
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config={
                    DENSE_VECTOR_NAME: VectorParams(
                        size=self.dense_dim,
                        distance=Distance.COSINE,
                        quantization_config=BinaryQuantization(
                            binary=BinaryQuantizationConfig(
                                always_ram=True,
                            ),
                        ),
                    ),
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                    ),
                },
            )
            logger.info("Collection '%s' created", self.collection)
        else:
            logger.info("Collection '%s' already exists", self.collection)

        # Create payload indices (may already exist)
        from qdrant_client.http.exceptions import UnexpectedResponse

        for field_name, field_type in INDEXED_FIELDS.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except UnexpectedResponse as e:
                if e.status_code == 400:
                    pass  # Index already exists
                else:
                    raise

        logger.info("Payload indices ensured for %d fields", len(INDEXED_FIELDS))

    def upsert_chunks(
        self,
        chunk_ids: list[str],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseVector],
        payloads: list[dict],
    ):
        """Upsert chunks with their dense and sparse vectors."""
        if not chunk_ids:
            return

        points = []
        for i, chunk_id in enumerate(chunk_ids):
            point = PointStruct(
                id=i,  # Will be overridden below
                vector={
                    DENSE_VECTOR_NAME: dense_vectors[i],
                    SPARSE_VECTOR_NAME: sparse_vectors[i],
                },
                payload={**payloads[i], "chunk_id": chunk_id},
            )
            points.append(point)

        # Upsert in batches of 100
        batch_size = 100
        for batch_start in range(0, len(points), batch_size):
            batch = points[batch_start : batch_start + batch_size]
            # Use chunk_id hash as point ID for idempotent upserts
            for j, point in enumerate(batch):
                point.id = _chunk_id_to_point_id(chunk_ids[batch_start + j])
            self.client.upsert(
                collection_name=self.collection,
                points=batch,
            )

        logger.info("Upserted %d points to '%s'", len(points), self.collection)

    def hybrid_search(
        self,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        limit: int = 30,
        scope_filter: str | None = None,
        entity_boost: list[str] | None = None,
    ) -> list[SearchHit]:
        """Run hybrid dense+sparse search with RRF fusion."""
        # Build optional filter
        must_conditions = []
        should_conditions = []

        if scope_filter and scope_filter != "all":
            must_conditions.append(
                FieldCondition(
                    key="folder_path",
                    match=MatchAny(any=[scope_filter]),
                )
            )

        if entity_boost:
            should_conditions.append(
                FieldCondition(
                    key="api_entities",
                    match=MatchAny(any=entity_boost),
                )
            )

        query_filter = None
        if must_conditions or should_conditions:
            query_filter = Filter(
                must=must_conditions if must_conditions else None,
                should=should_conditions if should_conditions else None,
            )

        # Prefetch: dense and sparse separately, then fuse with RRF
        prefetch = [
            Prefetch(
                query=NearestQuery(nearest=dense_vector),
                using=DENSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
            Prefetch(
                query=NearestQuery(nearest=sparse_vector),
                using=SPARSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
        ]

        results = self.client.query_points(
            collection_name=self.collection,
            prefetch=prefetch,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True,
        )

        hits = []
        for point in results.points:
            chunk_id = point.payload.get("chunk_id", "")
            hits.append(
                SearchHit(
                    chunk_id=chunk_id,
                    score=point.score,
                    payload=point.payload,
                )
            )

        return hits

    def get_by_chunk_ids(self, chunk_ids: list[str]) -> list[dict]:
        """Retrieve points by their chunk_id payload field."""
        if not chunk_ids:
            return []

        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="chunk_id",
                        match=MatchAny(any=chunk_ids),
                    )
                ]
            ),
            limit=len(chunk_ids),
            with_payload=True,
        )

        return [point.payload for point, _ in zip(results[0], range(len(chunk_ids)), strict=False)]

    def get_by_file_paths(
        self,
        file_paths: list[str],
        chunk_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve points matching any of the given file_path values."""
        if not file_paths:
            return []

        conditions = [
            FieldCondition(
                key="file_path",
                match=MatchAny(any=file_paths),
            )
        ]
        if chunk_types:
            conditions.append(
                FieldCondition(
                    key="chunk_type",
                    match=MatchAny(any=chunk_types),
                )
            )

        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(must=conditions),
            limit=limit,
            with_payload=True,
        )

        return [point.payload for point in results[0]]

    def delete_by_file_path(self, file_path: str):
        """Delete all points originating from a given file."""
        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="file_path",
                        match=MatchAny(any=[file_path]),
                    )
                ]
            ),
        )
        logger.info("Deleted points for file_path='%s'", file_path)

    def delete_by_chunk_ids(self, chunk_ids: list[str]):
        """Delete points matching any of the given chunk_id values."""
        if not chunk_ids:
            return
        # Qdrant point IDs are derived from chunk_id hashes
        point_ids = [_chunk_id_to_point_id(cid) for cid in chunk_ids]
        self.client.delete(
            collection_name=self.collection,
            points_selector=point_ids,
        )
        logger.info("Deleted %d points by chunk_id", len(chunk_ids))

    def collection_info(self) -> dict:
        """Return collection info as a dict."""
        info = self.client.get_collection(self.collection)
        return {
            "points_count": info.points_count,
            "status": info.status.value,
        }


def _chunk_id_to_point_id(chunk_id: str) -> int:
    """Convert a chunk_id string to a deterministic positive integer for Qdrant."""
    import hashlib

    h = hashlib.sha256(chunk_id.encode()).hexdigest()
    # Use first 15 hex chars to stay within int64 range
    return int(h[:15], 16)
