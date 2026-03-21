"""Integration tests against real PostgreSQL and Qdrant.

Requires: docker compose -f docker-compose.dev.yml up -d
Run with: uv run pytest -m integration tests/test_integration.py -v
"""

import contextlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.postgres import PostgresClient
from vue_docs_core.clients.qdrant import QdrantDocClient

PG_URL = "postgresql+psycopg://vue_mcp:vue_mcp@localhost:5432/vue_mcp"
QDRANT_URL = "http://localhost:6333"
TEST_COLLECTION = "vue_docs_integration_test"


@pytest.fixture()
def db():
    client = PostgresClient(PG_URL)
    client.create_tables()
    yield client
    client.close()


@pytest.fixture()
def qdrant():
    client = QdrantDocClient(url=QDRANT_URL, collection=TEST_COLLECTION, dense_dim=4)
    client.setup_collection(recreate=True)
    yield client
    with contextlib.suppress(Exception):
        client.client.delete_collection(TEST_COLLECTION)
    client.close()


@pytest.mark.integration
class TestPostgresIntegration:
    """Verify ORM operations against real PostgreSQL (not SQLite)."""

    def test_entities_round_trip(self, db: PostgresClient):
        entities = {
            "ref": {
                "entity_type": "composable",
                "page_path": "api/reactivity-core",
                "section": "ref()",
                "related": ["reactive", "unref"],
            },
        }
        db.save_entities(entities)
        result = db.load_entities()

        assert len(result.entities) == 1
        assert result.entities["ref"].entity_type == "composable"
        assert result.entities["ref"].related == ["reactive", "unref"]

    def test_synonyms_round_trip(self, db: PostgresClient):
        synonyms = {"two-way binding": ["v-model"], "lifecycle": ["onMounted"]}
        db.save_synonyms(synonyms)
        result = db.load_synonyms()

        assert result == synonyms

    def test_pages_round_trip(self, db: PostgresClient):
        db.save_pages({"guide/intro": "# Introduction\nWelcome."})
        assert db.read_page("guide/intro") == "# Introduction\nWelcome."
        assert db.read_page("nonexistent") is None

    def test_index_state_round_trip(self, db: PostgresClient):
        now = datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC)
        db.save_index_state("guide/intro.md", "abc123", "5", ["c1", "c2"], now)

        entry = db.load_index_state_entry("guide/intro.md")
        assert entry is not None
        assert entry["content_hash"] == "abc123"
        assert entry["chunk_ids"] == ["c1", "c2"]

    def test_bm25_model_round_trip(self, db: PostgresClient):
        model = BM25Model()
        model.fit(["vue reactivity", "computed properties", "watch deep"])

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "bm25"
            model.save(save_path)
            db.save_bm25_model(save_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            load_path = Path(tmpdir) / "bm25"
            assert db.load_bm25_model(load_path) is True

            loaded = BM25Model()
            loaded.load(load_path)
            assert loaded.vocab_size == model.vocab_size

    def test_pages_listing_from_index_state(self, db: PostgresClient):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        db.save_index_state("guide/intro.md", "h1", "5", ["c1"], now)
        db.save_index_state("api/ref.md", "h2", "5", ["c2"], now)

        paths, folders = db.load_pages_listing()
        assert "guide/intro.md" in paths
        assert "api/ref.md" in paths
        assert "guide" in folders
        assert "api" in folders


@pytest.mark.integration
class TestQdrantIntegration:
    """Verify collection operations against real Qdrant."""

    def test_collection_setup(self, qdrant: QdrantDocClient):
        info = qdrant.collection_info()
        assert info["points_count"] == 0

    def test_upsert_and_retrieve(self, qdrant: QdrantDocClient):
        from qdrant_client.models import SparseVector

        chunk_ids = ["test/chunk#0", "test/chunk#1"]
        dense_vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        sparse_vectors = [
            SparseVector(indices=[0, 1], values=[1.0, 0.5]),
            SparseVector(indices=[1, 2], values=[0.8, 0.3]),
        ]
        payloads = [
            {
                "content": "Vue computed properties",
                "chunk_type": "section",
                "folder_path": "guide",
                "file_path": "guide/computed.md",
                "api_style": "both",
                "api_entities": [],
                "global_sort_key": "01_00",
                "parent_chunk_id": "",
            },
            {
                "content": "Vue reactive references",
                "chunk_type": "section",
                "folder_path": "api",
                "file_path": "api/ref.md",
                "api_style": "both",
                "api_entities": [],
                "global_sort_key": "02_00",
                "parent_chunk_id": "",
            },
        ]

        qdrant.upsert_chunks(chunk_ids, dense_vectors, sparse_vectors, payloads)

        import time

        time.sleep(0.5)

        info = qdrant.collection_info()
        assert info["points_count"] == 2

        # Retrieve by chunk_id
        results = qdrant.get_by_chunk_ids(["test/chunk#0"])
        assert len(results) == 1
        assert results[0]["content"] == "Vue computed properties"

    def test_hybrid_search(self, qdrant: QdrantDocClient):
        from qdrant_client.models import SparseVector

        chunk_ids = ["search/chunk#0", "search/chunk#1"]
        dense_vectors = [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        sparse_vectors = [
            SparseVector(indices=[0], values=[1.0]),
            SparseVector(indices=[1], values=[1.0]),
        ]
        payloads = [
            {
                "content": "first",
                "chunk_type": "section",
                "folder_path": "guide",
                "file_path": "guide/a.md",
                "api_style": "both",
                "api_entities": [],
                "global_sort_key": "01",
                "parent_chunk_id": "",
                "chunk_id": "search/chunk#0",
            },
            {
                "content": "second",
                "chunk_type": "section",
                "folder_path": "guide",
                "file_path": "guide/b.md",
                "api_style": "both",
                "api_entities": [],
                "global_sort_key": "02",
                "parent_chunk_id": "",
                "chunk_id": "search/chunk#1",
            },
        ]

        qdrant.upsert_chunks(chunk_ids, dense_vectors, sparse_vectors, payloads)

        import time

        time.sleep(0.5)

        # Search with dense vector close to first chunk
        hits = qdrant.hybrid_search(
            dense_vector=[0.9, 0.1, 0.0, 0.0],
            sparse_vector=SparseVector(indices=[0], values=[0.8]),
            limit=2,
        )
        assert len(hits) >= 1
        assert hits[0].chunk_id == "search/chunk#0"

    def test_delete_by_chunk_ids(self, qdrant: QdrantDocClient):
        from qdrant_client.models import SparseVector

        chunk_ids = ["del/chunk#0", "del/chunk#1"]
        dense_vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        sparse_vectors = [
            SparseVector(indices=[0], values=[1.0]),
            SparseVector(indices=[1], values=[1.0]),
        ]
        payloads = [
            {
                "content": "to delete",
                "chunk_type": "section",
                "folder_path": "guide",
                "file_path": "guide/a.md",
                "api_style": "both",
                "api_entities": [],
                "global_sort_key": "01",
                "parent_chunk_id": "",
            },
            {
                "content": "to keep",
                "chunk_type": "section",
                "folder_path": "guide",
                "file_path": "guide/b.md",
                "api_style": "both",
                "api_entities": [],
                "global_sort_key": "02",
                "parent_chunk_id": "",
            },
        ]

        qdrant.upsert_chunks(chunk_ids, dense_vectors, sparse_vectors, payloads)

        import time

        time.sleep(0.5)

        qdrant.delete_by_chunk_ids(["del/chunk#0"])
        time.sleep(0.5)

        info = qdrant.collection_info()
        assert info["points_count"] == 1
