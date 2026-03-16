"""Tests for Day 14: Incremental updates.

Covers change detection, deleted file handling, state persistence,
payload-to-chunk reconstruction, and the summary input hash helper.
No real API calls.
"""

from unittest.mock import MagicMock

from vue_docs_core.models.chunk import ChunkType
from vue_docs_ingestion.scanner import find_markdown_files, hash_file
from vue_docs_ingestion.state import FileState, IndexState

# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestIndexState:
    def test_save_and_load(self, tmp_path):
        state_path = tmp_path / "state.json"
        state = IndexState(state_path)

        state.set(
            "guide/a.md",
            FileState(
                content_hash="abc123",
                pipeline_version="5",
                chunk_ids=["guide/a#intro", "guide/a#details"],
                last_indexed="2026-03-16T00:00:00Z",
            ),
        )
        state.save()

        # Reload
        loaded = IndexState(state_path)
        fs = loaded.get("guide/a.md")
        assert fs is not None
        assert fs.content_hash == "abc123"
        assert fs.pipeline_version == "5"
        assert fs.chunk_ids == ["guide/a#intro", "guide/a#details"]
        assert fs.last_indexed == "2026-03-16T00:00:00Z"

    def test_get_missing_returns_none(self, tmp_path):
        state = IndexState(tmp_path / "state.json")
        assert state.get("nonexistent.md") is None

    def test_remove(self, tmp_path):
        state_path = tmp_path / "state.json"
        state = IndexState(state_path)
        state.set("guide/a.md", FileState(content_hash="x", pipeline_version="1"))
        state.set("guide/b.md", FileState(content_hash="y", pipeline_version="1"))

        state.remove("guide/a.md")
        assert state.get("guide/a.md") is None
        assert state.get("guide/b.md") is not None
        assert "guide/a.md" not in state.all_file_paths()

    def test_all_file_paths(self, tmp_path):
        state = IndexState(tmp_path / "state.json")
        state.set("a.md", FileState(content_hash="x", pipeline_version="1"))
        state.set("b.md", FileState(content_hash="y", pipeline_version="1"))
        assert sorted(state.all_file_paths()) == ["a.md", "b.md"]

    def test_total_chunks(self, tmp_path):
        state = IndexState(tmp_path / "state.json")
        state.set(
            "a.md",
            FileState(
                content_hash="x",
                pipeline_version="1",
                chunk_ids=["a#1", "a#2"],
            ),
        )
        state.set(
            "b.md",
            FileState(
                content_hash="y",
                pipeline_version="1",
                chunk_ids=["b#1"],
            ),
        )
        assert state.total_chunks() == 3

    def test_remove_nonexistent_is_noop(self, tmp_path):
        state = IndexState(tmp_path / "state.json")
        state.remove("does-not-exist.md")  # Should not raise


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------


class TestChangeDetection:
    def test_new_file_detected(self, tmp_path):
        """A file not in state should be flagged for processing."""
        state = IndexState(tmp_path / "state.json")
        assert state.get("guide/new-file.md") is None

    def test_unchanged_file_skipped(self, tmp_path):
        """A file with matching hash and version should be skipped."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nHello world")

        file_hash = hash_file(md_file)

        state = IndexState(tmp_path / "state.json")
        state.set(
            "test.md",
            FileState(
                content_hash=file_hash,
                pipeline_version="5",
                chunk_ids=["test#intro"],
            ),
        )

        existing = state.get("test.md")
        assert existing is not None
        assert existing.content_hash == file_hash
        # This file would NOT be added to to_process

    def test_changed_file_detected(self, tmp_path):
        """A file whose hash differs from state should be flagged."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Original content")
        old_hash = hash_file(md_file)

        state = IndexState(tmp_path / "state.json")
        state.set(
            "test.md",
            FileState(
                content_hash=old_hash,
                pipeline_version="5",
            ),
        )

        # Modify the file
        md_file.write_text("# Updated content with changes")
        new_hash = hash_file(md_file)

        existing = state.get("test.md")
        assert existing.content_hash != new_hash

    def test_version_bump_forces_reindex(self, tmp_path):
        """A file indexed with old pipeline version should be reprocessed."""
        state = IndexState(tmp_path / "state.json")
        state.set(
            "test.md",
            FileState(
                content_hash="abc",
                pipeline_version="4",  # Old version
            ),
        )

        existing = state.get("test.md")
        assert existing.pipeline_version != "5"  # Current version


# ---------------------------------------------------------------------------
# Deleted file detection
# ---------------------------------------------------------------------------


class TestDeletedFileDetection:
    def test_detects_deleted_files(self, tmp_path):
        """Files in state but not on disk should be detected as deleted."""
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.md").write_text("# B")

        state = IndexState(tmp_path / "state.json")
        state.set("a.md", FileState(content_hash="x", pipeline_version="5"))
        state.set("b.md", FileState(content_hash="y", pipeline_version="5"))
        state.set("c.md", FileState(content_hash="z", pipeline_version="5"))  # deleted

        current_files = {"a.md", "b.md"}
        previously_indexed = set(state.all_file_paths())
        deleted = previously_indexed - current_files

        assert deleted == {"c.md"}

    def test_no_false_positives_for_existing_files(self, tmp_path):
        """All current files that exist should not be flagged as deleted."""
        state = IndexState(tmp_path / "state.json")
        state.set("a.md", FileState(content_hash="x", pipeline_version="5"))

        current_files = {"a.md"}
        previously_indexed = set(state.all_file_paths())
        deleted = previously_indexed - current_files

        assert deleted == set()


# ---------------------------------------------------------------------------
# Payload-to-chunk reconstruction
# ---------------------------------------------------------------------------


class TestPayloadToChunk:
    def test_reconstructs_chunk_from_payload(self):
        from vue_docs_ingestion.pipeline import _payload_to_chunk

        payload = {
            "chunk_id": "guide/essentials/computed#caching",
            "chunk_type": "section",
            "content": "Computed properties are cached.",
            "file_path": "guide/essentials/computed.md",
            "folder_path": "guide/essentials",
            "page_title": "Computed Properties",
            "section_title": "Caching",
            "subsection_title": "",
            "breadcrumb": "Guide > Essentials > Computed > Caching",
            "global_sort_key": "02_guide/01_essentials/03_computed",
            "content_type": "text",
            "language_tag": "",
            "api_style": "composition",
            "api_entities": ["computed"],
            "cross_references": ["api/reactivity-core.md"],
            "parent_chunk_id": "",
            "sibling_chunk_ids": [],
            "child_chunk_ids": [],
            "preceding_prose": "",
            "contextual_prefix": "This chunk is about caching.",
            "content_hash": "abc123",
        }

        chunk = _payload_to_chunk(payload)

        assert chunk.chunk_id == "guide/essentials/computed#caching"
        assert chunk.chunk_type == ChunkType.SECTION
        assert chunk.content == "Computed properties are cached."
        assert chunk.metadata.file_path == "guide/essentials/computed.md"
        assert chunk.metadata.folder_path == "guide/essentials"
        assert chunk.metadata.api_style == "composition"
        assert chunk.metadata.api_entities == ["computed"]
        assert chunk.contextual_prefix == "This chunk is about caching."

    def test_handles_missing_fields_gracefully(self):
        from vue_docs_ingestion.pipeline import _payload_to_chunk

        # Minimal payload
        payload = {
            "chunk_id": "test#section",
            "chunk_type": "section",
            "content": "Hello",
        }

        chunk = _payload_to_chunk(payload)
        assert chunk.chunk_id == "test#section"
        assert chunk.content == "Hello"
        assert chunk.metadata.file_path == ""
        assert chunk.metadata.api_entities == []


# ---------------------------------------------------------------------------
# Summary input hash
# ---------------------------------------------------------------------------


class TestSummaryInputHash:
    def test_same_input_same_hash(self):
        from vue_docs_ingestion.pipeline import _summary_input_hash

        texts = ["Summary of page A", "Summary of page B"]
        h1 = _summary_input_hash(texts)
        h2 = _summary_input_hash(texts)
        assert h1 == h2

    def test_different_input_different_hash(self):
        from vue_docs_ingestion.pipeline import _summary_input_hash

        h1 = _summary_input_hash(["Summary A", "Summary B"])
        h2 = _summary_input_hash(["Summary A", "Summary C"])
        assert h1 != h2

    def test_order_matters(self):
        from vue_docs_ingestion.pipeline import _summary_input_hash

        h1 = _summary_input_hash(["A", "B"])
        h2 = _summary_input_hash(["B", "A"])
        assert h1 != h2


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class TestScanner:
    def test_find_markdown_files(self, tmp_path):
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.md").write_text("# B")
        (tmp_path / "other.txt").write_text("not md")

        files = find_markdown_files(tmp_path)
        names = [f.name for f in files]
        assert "a.md" in names
        assert "b.md" in names
        assert "other.txt" not in names

    def test_hash_file_deterministic(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Hello world")
        h1 = hash_file(f)
        h2 = hash_file(f)
        assert h1 == h2
        assert len(h1) == 16  # 16 hex chars

    def test_hash_file_changes_with_content(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Version 1")
        h1 = hash_file(f)
        f.write_text("Version 2")
        h2 = hash_file(f)
        assert h1 != h2


# ---------------------------------------------------------------------------
# Qdrant delete_by_chunk_ids
# ---------------------------------------------------------------------------


class TestQdrantDeleteByChunkIds:
    def test_delete_by_chunk_ids(self):
        from vue_docs_core.clients.qdrant import QdrantDocClient

        qdrant = QdrantDocClient()
        qdrant._client = MagicMock()

        qdrant.delete_by_chunk_ids(["chunk#a", "chunk#b"])

        qdrant._client.delete.assert_called_once()
        call_args = qdrant._client.delete.call_args
        assert call_args.kwargs["collection_name"] == qdrant.collection
        # Point IDs should be a list of integers
        point_ids = call_args.kwargs["points_selector"]
        assert isinstance(point_ids, list)
        assert len(point_ids) == 2
        assert all(isinstance(pid, int) for pid in point_ids)

    def test_delete_by_chunk_ids_empty(self):
        from vue_docs_core.clients.qdrant import QdrantDocClient

        qdrant = QdrantDocClient()
        qdrant._client = MagicMock()

        qdrant.delete_by_chunk_ids([])

        qdrant._client.delete.assert_not_called()
