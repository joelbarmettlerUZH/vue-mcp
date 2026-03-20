"""Tests for Jina client, BM25, and Qdrant collection setup and hybrid search."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import SparseVector

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.jina import (
    TASK_RETRIEVAL_PASSAGE,
    TASK_RETRIEVAL_QUERY,
    EmbeddingResult,
    JinaClient,
)
from vue_docs_core.clients.qdrant import QdrantDocClient, _chunk_id_to_point_id

# ---------------------------------------------------------------------------
# BM25 tests (no API calls)
# ---------------------------------------------------------------------------


class TestBM25Model:
    CORPUS = [
        "Vue computed properties are cached based on reactive dependencies.",
        "Reactive state management with ref and reactive composables.",
        "Component lifecycle hooks like onMounted and onUnmounted.",
        "Template syntax uses v-bind v-for v-if directives.",
    ]

    def test_fit_creates_vocab(self):
        model = BM25Model()
        assert not model.is_fitted
        model.fit(self.CORPUS)
        assert model.is_fitted
        assert model.vocab_size > 0

    def test_vocab_contains_key_terms(self):
        model = BM25Model()
        model.fit(self.CORPUS)
        assert "computed" in model._vocab
        assert "reactive" in model._vocab
        assert "lifecycle" in model._vocab

    def test_doc_sparse_vectors_count(self):
        model = BM25Model()
        model.fit(self.CORPUS)
        vectors = model.get_doc_sparse_vectors(self.CORPUS)
        assert len(vectors) == len(self.CORPUS)

    def test_doc_sparse_vectors_structure(self):
        model = BM25Model()
        model.fit(self.CORPUS)
        vectors = model.get_doc_sparse_vectors(self.CORPUS)
        for vec in vectors:
            assert isinstance(vec, SparseVector)
            assert len(vec.indices) > 0
            assert len(vec.indices) == len(vec.values)
            assert all(v > 0 for v in vec.values)

    def test_doc_sparse_vectors_are_per_doc(self):
        model = BM25Model()
        model.fit(self.CORPUS)
        vectors = model.get_doc_sparse_vectors(self.CORPUS)
        # All vectors should differ since corpora differ
        index_sets = [frozenset(v.indices) for v in vectors]
        assert len(set(index_sets)) == len(self.CORPUS)

    def test_query_sparse_vector_known_tokens(self):
        model = BM25Model()
        model.fit(self.CORPUS)
        vec = model.get_query_sparse_vector("computed reactive")
        assert isinstance(vec, SparseVector)
        assert len(vec.indices) > 0
        # Values should be 1.0 for query vectors
        assert all(v == 1.0 for v in vec.values)

    def test_query_sparse_vector_unknown_tokens(self):
        model = BM25Model()
        model.fit(self.CORPUS)
        # Completely unknown tokens → returns fallback zero vector
        vec = model.get_query_sparse_vector("xyzzy foobar quux")
        assert isinstance(vec, SparseVector)
        assert len(vec.indices) == 1  # Fallback
        assert vec.values[0] == 0.0

    def test_query_sparse_vector_deduplicates(self):
        model = BM25Model()
        model.fit(self.CORPUS)
        vec = model.get_query_sparse_vector("computed computed computed")
        # 'computed' appears once in vocab → one index
        assert vec.indices.count(vec.indices[0]) == 1

    def test_not_fitted_raises(self):
        model = BM25Model()
        with pytest.raises(RuntimeError, match="not fitted"):
            model.get_doc_sparse_vectors(["text"])
        with pytest.raises(RuntimeError, match="not fitted"):
            model.get_query_sparse_vector("query")

    def test_save_and_load(self, tmp_path):
        model = BM25Model()
        model.fit(self.CORPUS)
        model.save(tmp_path / "bm25")

        loaded = BM25Model()
        loaded.load(tmp_path / "bm25")
        assert loaded.is_fitted
        assert loaded._vocab == model._vocab

        # Query should produce same result
        v1 = model.get_query_sparse_vector("computed reactive")
        v2 = loaded.get_query_sparse_vector("computed reactive")
        assert v1.indices == v2.indices
        assert v1.values == v2.values


# ---------------------------------------------------------------------------
# Jina client tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestJinaClientEmbed:
    def _make_response(self, dims: int = 1024, n: int = 1, tokens: int = 10) -> dict:
        return {
            "data": [{"embedding": [0.1] * dims, "index": i} for i in range(n)],
            "usage": {"total_tokens": tokens},
        }

    @pytest.mark.asyncio
    async def test_embed_returns_correct_shape(self):
        client = JinaClient(api_key="test-key", model="jina-embeddings-v4")
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_response(1024, 2, 20)
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            client,
            "_request_with_retry",
            new=AsyncMock(return_value=self._make_response(1024, 2, 20)),
        ):
            result = await client.embed(["text one", "text two"])

        assert len(result.embeddings) == 2
        assert len(result.embeddings[0]) == 1024
        assert result.total_tokens == 20

    @pytest.mark.asyncio
    async def test_embed_batched_splits_correctly(self):
        client = JinaClient(api_key="test-key", model="jina-embeddings-v4")
        texts = [f"text {i}" for i in range(10)]
        call_count = 0

        async def fake_embed(batch_texts, task=TASK_RETRIEVAL_PASSAGE):
            nonlocal call_count
            call_count += 1
            return EmbeddingResult(
                embeddings=[[0.1] * 1024] * len(batch_texts),
                total_tokens=len(batch_texts) * 5,
            )

        with patch.object(client, "embed", side_effect=fake_embed):
            result = await client.embed_batched(texts, batch_size=4)

        assert len(result.embeddings) == 10
        assert call_count == 3  # 4 + 4 + 2

    @pytest.mark.asyncio
    async def test_rerank_returns_indices_and_scores(self):
        client = JinaClient(api_key="test-key")
        mock_data = {
            "results": [
                {"index": 2, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.72},
                {"index": 1, "relevance_score": 0.31},
            ],
            "usage": {"total_tokens": 500},
        }
        with patch.object(client, "_request_with_retry", new=AsyncMock(return_value=mock_data)):
            result = await client.rerank("query", ["doc0", "doc1", "doc2"])

        assert result.indices == [2, 0, 1]
        assert result.scores[0] == pytest.approx(0.95)
        assert result.total_tokens == 500


# ---------------------------------------------------------------------------
# Qdrant utility tests (no network)
# ---------------------------------------------------------------------------


class TestChunkIdToPointId:
    def test_deterministic(self):
        a = _chunk_id_to_point_id("guide/essentials/computed#writable-computed")
        b = _chunk_id_to_point_id("guide/essentials/computed#writable-computed")
        assert a == b

    def test_unique(self):
        ids = {_chunk_id_to_point_id(f"chunk#{i}") for i in range(1000)}
        assert len(ids) == 1000

    def test_positive_int(self):
        val = _chunk_id_to_point_id("any-chunk-id")
        assert isinstance(val, int)
        assert val > 0


# ---------------------------------------------------------------------------
# Live integration test: Jina embed + Qdrant upsert + search
# (only runs when JINA_API_KEY and QDRANT_URL are set in .env)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLiveIntegration:
    """End-to-end test using real Jina and Qdrant APIs."""

    COLLECTION = "vue_docs_test_day4"
    TEXTS = [
        "Vue computed properties cache based on reactive dependencies.",
        "The ref() function creates a reactive reference to a value.",
        "Component lifecycle hooks run at specific stages of the component lifecycle.",
        "v-for directive renders a list of items from an array.",
    ]

    @pytest.mark.asyncio
    async def test_embed_upsert_search(self):

        jina = JinaClient()
        qdrant = QdrantDocClient(collection=self.COLLECTION, dense_dim=1024)

        try:
            # 1. Setup collection (recreate to ensure clean state)
            qdrant.setup_collection(recreate=True)
            info = qdrant.collection_info()
            assert info["points_count"] == 0

            # 2. Embed all texts
            embed_result = await jina.embed_batched(self.TEXTS, task=TASK_RETRIEVAL_PASSAGE)
            assert len(embed_result.embeddings) == len(self.TEXTS)
            assert len(embed_result.embeddings[0]) == 1024

            # 3. BM25 sparse vectors
            bm25 = BM25Model()
            bm25.fit(self.TEXTS)
            sparse_vecs = bm25.get_doc_sparse_vectors(self.TEXTS)

            # 4. Upsert
            chunk_ids = [f"test/chunk#{i}" for i in range(len(self.TEXTS))]
            payloads = [
                {
                    "content": t,
                    "chunk_type": "section",
                    "folder_path": "guide",
                    "file_path": f"guide/test{i}.md",
                    "api_style": "both",
                    "api_entities": [],
                    "global_sort_key": f"01_{i:02d}",
                    "parent_chunk_id": "",
                }
                for i, t in enumerate(self.TEXTS)
            ]
            qdrant.upsert_chunks(
                chunk_ids=chunk_ids,
                dense_vectors=embed_result.embeddings,
                sparse_vectors=sparse_vecs,
                payloads=payloads,
            )

            # Wait for indexing to propagate
            import time

            time.sleep(1)

            info = qdrant.collection_info()
            assert info["points_count"] == len(self.TEXTS)

            # 5. Query
            query = "how does computed caching work in Vue?"
            query_embed = await jina.embed([query], task=TASK_RETRIEVAL_QUERY)
            query_dense = query_embed.embeddings[0]
            query_sparse = bm25.get_query_sparse_vector(query)

            hits = qdrant.hybrid_search(
                dense_vector=query_dense,
                sparse_vector=query_sparse,
                limit=4,
            )
            assert len(hits) > 0
            # The computed properties chunk should rank first
            top_chunk_id = hits[0].chunk_id
            assert "chunk#0" in top_chunk_id  # computed properties text is index 0

        finally:
            # Cleanup test collection
            with contextlib.suppress(Exception):
                qdrant.client.delete_collection(self.COLLECTION)
            await jina.close()
