"""Tests for the PostgresClient using an in-memory SQLite backend.

SQLite lacks JSONB and GREATEST, so we patch minimally: JSONB → JSON,
and test get_max_updated_at separately. This validates all ORM logic,
serialization, and round-trip correctness without requiring a real PG instance.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.postgres import (
    EntityRow,
    IndexStateRow,
    PostgresClient,
    SynonymRow,
)
from vue_docs_core.models.entity import EntityIndex


def _make_client() -> PostgresClient:
    """Create a PostgresClient backed by in-memory SQLite."""
    # Patch JSONB columns to use plain JSON for SQLite compatibility
    for _col_name, col in EntityRow.__table__.columns.items():
        if hasattr(col.type, "__class__") and col.type.__class__.__name__ == "JSONB":
            col.type = JSON()
    for _col_name, col in SynonymRow.__table__.columns.items():
        if hasattr(col.type, "__class__") and col.type.__class__.__name__ == "JSONB":
            col.type = JSON()
    for _col_name, col in IndexStateRow.__table__.columns.items():
        if hasattr(col.type, "__class__") and col.type.__class__.__name__ == "JSONB":
            col.type = JSON()

    client = PostgresClient("sqlite:///:memory:")
    client.create_tables()
    return client


class TestEntities:
    def test_save_and_load_entities(self):
        db = _make_client()
        entities = {
            "ref": {
                "entity_type": "composable",
                "page_path": "api/reactivity-core",
                "section": "ref()",
                "related": ["reactive", "unref"],
            },
            "computed": {
                "entity_type": "composable",
                "page_path": "api/reactivity-core",
                "section": "computed()",
                "related": [],
            },
        }
        db.save_entities(entities)
        result = db.load_entities()

        assert isinstance(result, EntityIndex)
        assert len(result.entities) == 2
        assert result.entities["ref"].entity_type == "composable"
        assert result.entities["ref"].related == ["reactive", "unref"]
        assert result.entities["computed"].section == "computed()"
        db.close()

    def test_save_entities_replaces_all(self):
        db = _make_client()
        db.save_entities({"old": {"entity_type": "global_api", "page_path": "", "section": ""}})
        db.save_entities({"new": {"entity_type": "component", "page_path": "", "section": ""}})
        result = db.load_entities()

        assert len(result.entities) == 1
        assert "new" in result.entities
        assert "old" not in result.entities
        db.close()

    def test_load_entities_empty(self):
        db = _make_client()
        result = db.load_entities()
        assert len(result.entities) == 0
        db.close()


class TestSynonyms:
    def test_save_and_load_synonyms(self):
        db = _make_client()
        synonyms = {
            "two-way binding": ["v-model"],
            "lifecycle": ["onMounted", "onUnmounted"],
        }
        db.save_synonyms(synonyms)
        result = db.load_synonyms()

        assert len(result) == 2
        assert result["two-way binding"] == ["v-model"]
        assert result["lifecycle"] == ["onMounted", "onUnmounted"]
        db.close()

    def test_save_synonyms_replaces_all(self):
        db = _make_client()
        db.save_synonyms({"old": ["x"]})
        db.save_synonyms({"new": ["y"]})
        result = db.load_synonyms()

        assert len(result) == 1
        assert "new" in result
        db.close()


class TestPages:
    def test_save_and_read_page(self):
        db = _make_client()
        db.save_pages({"guide/intro": "# Introduction\nWelcome to Vue."})
        content = db.read_page("guide/intro")

        assert content == "# Introduction\nWelcome to Vue."
        db.close()

    def test_read_page_not_found(self):
        db = _make_client()
        assert db.read_page("nonexistent") is None
        db.close()

    def test_save_pages_upsert(self):
        db = _make_client()
        db.save_pages({"guide/intro": "v1"})
        db.save_pages({"guide/intro": "v2"})
        assert db.read_page("guide/intro") == "v2"
        db.close()

    def test_load_pages_listing(self):
        db = _make_client()
        # Pages listing comes from index_state, not pages table
        db.save_index_state(
            "guide/intro.md", "hash1", "5", ["c1"], datetime(2026, 1, 1, tzinfo=UTC)
        )
        db.save_index_state(
            "guide/advanced/slots.md", "hash2", "5", ["c2"], datetime(2026, 1, 1, tzinfo=UTC)
        )
        db.save_index_state("api/ref.md", "hash3", "5", ["c3"], datetime(2026, 1, 1, tzinfo=UTC))

        paths, folders = db.load_pages_listing()

        assert len(paths) == 3
        assert paths == ["api/ref.md", "guide/advanced/slots.md", "guide/intro.md"]
        assert "guide" in folders
        assert "guide/advanced" in folders
        assert "api" in folders
        db.close()


class TestIndexState:
    def test_save_and_load_entry(self):
        db = _make_client()
        db.save_index_state(
            file_path="guide/intro.md",
            content_hash="abc123",
            pipeline_version="5",
            chunk_ids=["c1", "c2", "c3"],
            last_indexed=datetime(2026, 3, 19, 12, 0, 0, tzinfo=UTC),
        )
        entry = db.load_index_state_entry("guide/intro.md")

        assert entry is not None
        assert entry["content_hash"] == "abc123"
        assert entry["pipeline_version"] == "5"
        assert entry["chunk_ids"] == ["c1", "c2", "c3"]
        db.close()

    def test_load_entry_not_found(self):
        db = _make_client()
        assert db.load_index_state_entry("nonexistent") is None
        db.close()

    def test_upsert_overwrites(self):
        db = _make_client()
        db.save_index_state("f.md", "hash1", "5", ["c1"], datetime(2026, 1, 1, tzinfo=UTC))
        db.save_index_state("f.md", "hash2", "6", ["c1", "c2"], datetime(2026, 1, 2, tzinfo=UTC))
        entry = db.load_index_state_entry("f.md")

        assert entry["content_hash"] == "hash2"
        assert entry["pipeline_version"] == "6"
        assert entry["chunk_ids"] == ["c1", "c2"]
        db.close()

    def test_remove_index_state(self):
        db = _make_client()
        db.save_index_state("f.md", "hash", "5", [], datetime(2026, 1, 1, tzinfo=UTC))
        db.remove_index_state("f.md")
        assert db.load_index_state_entry("f.md") is None
        db.close()

    def test_remove_nonexistent_is_noop(self):
        db = _make_client()
        db.remove_index_state("nonexistent")  # Should not raise
        db.close()

    def test_all_file_paths(self):
        db = _make_client()
        db.save_index_state("b.md", "h", "5", [], datetime(2026, 1, 1, tzinfo=UTC))
        db.save_index_state("a.md", "h", "5", [], datetime(2026, 1, 1, tzinfo=UTC))
        db.save_index_state("c.md", "h", "5", [], datetime(2026, 1, 1, tzinfo=UTC))

        paths = db.all_index_file_paths()
        assert paths == ["a.md", "b.md", "c.md"]
        db.close()

    def test_total_chunks(self):
        db = _make_client()
        db.save_index_state("a.md", "h", "5", ["c1", "c2"], datetime(2026, 1, 1, tzinfo=UTC))
        db.save_index_state("b.md", "h", "5", ["c3"], datetime(2026, 1, 1, tzinfo=UTC))

        assert db.total_index_chunks() == 3
        db.close()


class TestBm25Model:
    def test_save_and_load_bm25_model(self):
        db = _make_client()

        # Fit a real BM25 model
        model = BM25Model()
        model.fit(["vue reactivity system", "computed properties caching", "watch deep option"])

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "bm25_model"
            model.save(save_path)
            db.save_bm25_model(save_path)

        # Load it back
        with tempfile.TemporaryDirectory() as tmpdir:
            load_path = Path(tmpdir) / "bm25_model"
            found = db.load_bm25_model(load_path)
            assert found is True
            assert (load_path / "bm25s_model").exists()
            assert (load_path / "vocab.json").exists()

            loaded_model = BM25Model()
            loaded_model.load(load_path)
            assert loaded_model.vocab_size == model.vocab_size
        db.close()

    def test_load_bm25_model_not_found(self):
        db = _make_client()
        with tempfile.TemporaryDirectory() as tmpdir:
            found = db.load_bm25_model(Path(tmpdir) / "bm25")
            assert found is False
        db.close()


class TestCreateTables:
    def test_create_tables_idempotent(self):
        db = _make_client()
        db.create_tables()  # Second call should not raise
        db.save_pages({"test": "content"})
        assert db.read_page("test") == "content"
        db.close()
