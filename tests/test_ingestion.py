"""Tests for Day 5 ingestion pipeline components.

Covers scanner, state, embedder, indexer, and the CLI dry-run path.
No real API calls — Jina and Qdrant are mocked throughout.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import SparseVector

from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType
from vue_docs_ingestion.embedder import embed_dense
from vue_docs_ingestion.indexer import _chunk_payload, upsert_chunks_batch
from vue_docs_ingestion.scanner import find_markdown_files, hash_file
from vue_docs_ingestion.state import FileState, IndexState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    chunk_id: str = "guide/essentials/computed#computed-caching",
    content: str = "Computed properties are cached.",
    file_path: str = "guide/essentials/computed.md",
    folder_path: str = "guide/essentials",
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        chunk_type=ChunkType.SECTION,
        content=content,
        metadata=ChunkMetadata(
            file_path=file_path,
            folder_path=folder_path,
            page_title="Computed Properties",
            section_title="Computed Caching",
            subsection_title="",
            breadcrumb="Guide > Essentials > Computed Properties",
            global_sort_key="01_00_02",
            content_type="text",
            language_tag="",
            api_style="both",
            api_entities=[],
            cross_references=[],
        ),
        content_hash="abc123",
    )


# ---------------------------------------------------------------------------
# scanner.py
# ---------------------------------------------------------------------------


class TestScanner:
    def test_find_markdown_files_discovers_md_files(self, tmp_path):
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.md").write_text("# B")
        (tmp_path / "ignore.txt").write_text("text")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.md").write_text("# C")

        files = find_markdown_files(tmp_path)
        names = [f.name for f in files]
        assert "a.md" in names
        assert "b.md" in names
        assert "c.md" in names
        assert "ignore.txt" not in names

    def test_find_markdown_files_returns_sorted(self, tmp_path):
        for name in ["z.md", "a.md", "m.md"]:
            (tmp_path / name).write_text("")
        files = find_markdown_files(tmp_path)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_find_markdown_files_empty_dir(self, tmp_path):
        assert find_markdown_files(tmp_path) == []

    def test_hash_file_is_deterministic(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_bytes(b"hello world")
        h1 = hash_file(f)
        h2 = hash_file(f)
        assert h1 == h2

    def test_hash_file_length(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_bytes(b"content")
        h = hash_file(f)
        assert len(h) == 16

    def test_hash_file_changes_with_content(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_bytes(b"version one")
        h1 = hash_file(f)
        f.write_bytes(b"version two")
        h2 = hash_file(f)
        assert h1 != h2

    def test_hash_file_hex_characters_only(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_bytes(b"any content")
        h = hash_file(f)
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# state.py
# ---------------------------------------------------------------------------


def _mock_db():
    """Create a mock PostgresClient for IndexState tests."""
    db = MagicMock()
    db._store = {}

    def load_entry(file_path, source="vue"):
        return db._store.get((source, file_path))

    def save_entry(
        file_path, content_hash, pipeline_version, chunk_ids, last_indexed, source="vue"
    ):
        db._store[(source, file_path)] = {
            "content_hash": content_hash,
            "pipeline_version": pipeline_version,
            "chunk_ids": chunk_ids,
            "last_indexed": last_indexed,
        }

    def remove_entry(file_path, source="vue"):
        db._store.pop((source, file_path), None)

    def all_paths(source=None):
        return [fp for (s, fp) in db._store if source is None or s == source]

    def total_chunks(source=None):
        return sum(
            len(v["chunk_ids"]) for (s, _), v in db._store.items() if source is None or s == source
        )

    db.load_index_state_entry = MagicMock(side_effect=load_entry)
    db.save_index_state = MagicMock(side_effect=save_entry)
    db.remove_index_state = MagicMock(side_effect=remove_entry)
    db.all_index_file_paths = MagicMock(side_effect=all_paths)
    db.total_index_chunks = MagicMock(side_effect=total_chunks)
    return db


class TestIndexState:
    def test_get_missing_returns_none(self):
        db = _mock_db()
        state = IndexState(db=db)
        assert state.get("nonexistent.md") is None

    def test_set_and_get_roundtrip(self):
        db = _mock_db()
        state = IndexState(db=db)
        fs = FileState(
            content_hash="abc123",
            pipeline_version="1",
            chunk_ids=["chunk#1", "chunk#2"],
            last_indexed="2026-01-01T00:00:00+00:00",
        )
        state.set("guide/computed.md", fs)
        result = state.get("guide/computed.md")
        assert result is not None
        assert result.content_hash == "abc123"
        assert result.pipeline_version == "1"
        assert result.chunk_ids == ["chunk#1", "chunk#2"]
        assert result.last_indexed == "2026-01-01T00:00:00+00:00"

    def test_remove(self):
        db = _mock_db()
        state = IndexState(db=db)
        state.set("file.md", FileState(content_hash="x", pipeline_version="1"))
        state.remove("file.md")
        assert state.get("file.md") is None

    def test_remove_nonexistent_is_noop(self):
        db = _mock_db()
        state = IndexState(db=db)
        state.remove("does-not-exist.md")  # should not raise

    def test_all_file_paths(self):
        db = _mock_db()
        state = IndexState(db=db)
        state.set("a.md", FileState(content_hash="1", pipeline_version="1"))
        state.set("b.md", FileState(content_hash="2", pipeline_version="1"))
        paths = state.all_file_paths()
        assert set(paths) == {"a.md", "b.md"}

    def test_save_is_noop(self):
        db = _mock_db()
        state = IndexState(db=db)
        state.set(
            "file.md", FileState(content_hash="hash1", pipeline_version="1", chunk_ids=["c1"])
        )
        state.save()  # Should not raise (no-op for PG)

    def test_total_chunks(self):
        db = _mock_db()
        state = IndexState(db=db)
        state.set("a.md", FileState(content_hash="1", pipeline_version="1", chunk_ids=["c1", "c2"]))
        state.set("b.md", FileState(content_hash="2", pipeline_version="1", chunk_ids=["c3"]))
        assert state.total_chunks() == 3


# ---------------------------------------------------------------------------
# embedder.py
# ---------------------------------------------------------------------------


class TestEmbedder:
    @pytest.mark.asyncio
    async def test_embed_dense_returns_correct_count(self):
        from vue_docs_core.clients.jina import EmbeddingResult, JinaClient

        chunks = [_make_chunk(chunk_id=f"chunk#{i}") for i in range(5)]
        fake_result = EmbeddingResult(
            embeddings=[[0.1] * 1024] * 5,
            total_tokens=250,
        )

        with patch.object(JinaClient, "embed", new=AsyncMock(return_value=fake_result)):
            client = JinaClient(api_key="test")
            result = await embed_dense(chunks, client)

        assert len(result.vectors) == 5
        assert result.total_tokens == 250

    @pytest.mark.asyncio
    async def test_embed_dense_empty_input(self):
        from vue_docs_core.clients.jina import JinaClient

        client = JinaClient(api_key="test")
        result = await embed_dense([], client)
        assert result.vectors == []
        assert result.total_tokens == 0

    @pytest.mark.asyncio
    async def test_embed_dense_passes_chunk_content(self):
        from vue_docs_core.clients.jina import EmbeddingResult, JinaClient

        chunks = [_make_chunk(content="special content")]
        captured_texts = []

        async def fake_embed_batched(texts, task, batch_size=256):
            captured_texts.extend(texts)
            return EmbeddingResult(embeddings=[[0.0] * 1024], total_tokens=5)

        client = JinaClient(api_key="test")
        with patch.object(client, "embed_batched", side_effect=fake_embed_batched):
            await embed_dense(chunks, client)

        assert captured_texts == ["special content"]

    @pytest.mark.asyncio
    async def test_embed_dense_uses_batched(self):
        """embed_dense should use embed_batched, not embed."""
        from vue_docs_core.clients.jina import EmbeddingResult, JinaClient

        chunks = [_make_chunk(chunk_id=f"chunk#{i}") for i in range(10)]

        async def fake_embed_batched(texts, task, batch_size=256):
            return EmbeddingResult(
                embeddings=[[0.1] * 1024] * len(texts),
                total_tokens=len(texts) * 5,
            )

        client = JinaClient(api_key="test")
        with patch.object(client, "embed_batched", side_effect=fake_embed_batched):
            result = await embed_dense(chunks, client)

        assert len(result.vectors) == 10
        assert result.total_tokens == 50


# ---------------------------------------------------------------------------
# indexer.py
# ---------------------------------------------------------------------------


class TestIndexer:
    def test_chunk_payload_includes_required_fields(self):
        chunk = _make_chunk()
        payload = _chunk_payload(chunk)

        assert payload["file_path"] == "guide/essentials/computed.md"
        assert payload["folder_path"] == "guide/essentials"
        assert payload["chunk_type"] == "section"
        assert payload["content"] == "Computed properties are cached."
        assert payload["content_hash"] == "abc123"
        assert payload["api_style"] == "both"
        assert payload["api_entities"] == []
        assert payload["cross_references"] == []

    def test_chunk_payload_code_block_includes_language(self):
        chunk = _make_chunk()
        chunk.chunk_type = ChunkType.CODE_BLOCK
        chunk.metadata.language_tag = "vue"
        chunk.metadata.content_type = "code"
        payload = _chunk_payload(chunk)
        assert payload["language_tag"] == "vue"
        assert payload["content_type"] == "code"

    def test_upsert_chunks_batch_calls_qdrant(self):
        from vue_docs_core.clients.qdrant import QdrantDocClient

        chunks = [_make_chunk(chunk_id=f"chunk#{i}") for i in range(3)]
        dense = [[0.1] * 1024] * 3
        sparse = [SparseVector(indices=[0, 1], values=[0.5, 0.3])] * 3

        qdrant = MagicMock(spec=QdrantDocClient)
        upsert_chunks_batch(chunks, dense, sparse, qdrant)

        qdrant.upsert_chunks.assert_called_once()
        call_kwargs = qdrant.upsert_chunks.call_args.kwargs
        assert len(call_kwargs["chunk_ids"]) == 3
        assert len(call_kwargs["dense_vectors"]) == 3
        assert len(call_kwargs["sparse_vectors"]) == 3
        assert len(call_kwargs["payloads"]) == 3

    def test_upsert_chunks_batch_chunk_ids_match_chunks(self):
        from vue_docs_core.clients.qdrant import QdrantDocClient

        chunks = [
            _make_chunk(chunk_id="guide/a#section-1"),
            _make_chunk(chunk_id="guide/b#section-2"),
        ]
        dense = [[0.1] * 1024] * 2
        sparse = [SparseVector(indices=[0], values=[1.0])] * 2

        qdrant = MagicMock(spec=QdrantDocClient)
        upsert_chunks_batch(chunks, dense, sparse, qdrant)

        call_kwargs = qdrant.upsert_chunks.call_args.kwargs
        assert call_kwargs["chunk_ids"] == ["guide/a#section-1", "guide/b#section-2"]


# ---------------------------------------------------------------------------
# Pipeline dry-run (no API calls)
# ---------------------------------------------------------------------------


def _vue_source():
    """Return the Vue source definition for pipeline tests."""
    from vue_docs_core.data.sources import SOURCE_REGISTRY

    return SOURCE_REGISTRY["vue"]


class TestPipelineDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_jina_or_qdrant(self, tmp_path):
        """Dry-run should discover files and exit without touching external APIs."""
        docs = tmp_path / "src"
        docs.mkdir()
        (docs / "index.md").write_text("# Vue\nIntroduction.")

        data = tmp_path / "data"
        data.mkdir()

        mock_db = _mock_db()

        from vue_docs_ingestion.pipeline import run_pipeline

        with (
            patch("vue_docs_ingestion.pipeline.JinaClient") as MockJina,
            patch("vue_docs_ingestion.pipeline.QdrantDocClient") as MockQdrant,
        ):
            await run_pipeline(
                docs_path=docs, data_path=data, dry_run=True, db=mock_db, source=_vue_source()
            )

        MockJina.return_value.embed_batched.assert_not_called()
        MockQdrant.return_value.upsert_chunks.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_with_no_changes_exits_early(self, tmp_path):
        """If all files are up-to-date, the pipeline should exit before any API call."""
        docs = tmp_path / "src"
        docs.mkdir()
        md_file = docs / "test.md"
        md_file.write_text("# Test\nContent.")

        data = tmp_path / "data"
        data.mkdir()

        from vue_docs_core.config import settings as app_settings

        mock_db = _mock_db()
        state = IndexState(db=mock_db)
        state.set(
            "test.md",
            FileState(
                content_hash=hash_file(md_file),
                pipeline_version=app_settings.pipeline_version,
                chunk_ids=["test#intro"],
                last_indexed="2026-01-01T00:00:00+00:00",
            ),
        )

        from vue_docs_ingestion.pipeline import run_pipeline

        with (
            patch("vue_docs_ingestion.pipeline.JinaClient") as MockJina,
            patch("vue_docs_ingestion.pipeline.QdrantDocClient") as MockQdrant,
        ):
            await run_pipeline(docs_path=docs, data_path=data, db=mock_db, source=_vue_source())

        MockJina.return_value.embed_batched.assert_not_called()
        MockQdrant.return_value.upsert_chunks.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_flag_reprocesses_all_files(self, tmp_path):
        """--full should mark all files for processing even if their hash hasn't changed."""
        docs = tmp_path / "src"
        docs.mkdir()
        md_file = docs / "test.md"
        md_file.write_text("# Test\n\n## Section\n\nContent here.")

        data = tmp_path / "data"
        data.mkdir()

        from vue_docs_core.config import settings as app_settings

        mock_db = _mock_db()
        state = IndexState(db=mock_db)
        state.set(
            "test.md",
            FileState(
                content_hash=hash_file(md_file),
                pipeline_version=app_settings.pipeline_version,
                chunk_ids=["test#section"],
                last_indexed="2026-01-01T00:00:00+00:00",
            ),
        )

        from vue_docs_core.clients.jina import EmbeddingResult
        from vue_docs_ingestion.pipeline import run_pipeline

        mock_qdrant = MagicMock()
        mock_qdrant.setup_collection.return_value = None
        mock_qdrant.collection_info.return_value = {"points_count": 1, "status": "green"}
        mock_qdrant.delete_by_file_path.return_value = None
        mock_qdrant.upsert_chunks.return_value = None
        mock_qdrant.close.return_value = None

        mock_jina = MagicMock()

        async def dynamic_embed(texts, task, batch_size=64):
            return EmbeddingResult(embeddings=[[0.1] * 1024] * len(texts), total_tokens=100)

        mock_jina.embed_batched = AsyncMock(side_effect=dynamic_embed)
        mock_jina.close = AsyncMock()

        mock_gemini = MagicMock()
        mock_gemini.enrich_chunk = AsyncMock(return_value="enriched")
        mock_gemini.generate_hype_questions = AsyncMock(return_value=[])
        mock_gemini.close = AsyncMock()

        with (
            patch("vue_docs_ingestion.pipeline.JinaClient", return_value=mock_jina),
            patch("vue_docs_ingestion.pipeline.QdrantDocClient", return_value=mock_qdrant),
            patch("vue_docs_ingestion.pipeline.GeminiClient", return_value=mock_gemini),
            patch("vue_docs_ingestion.pipeline.settings") as mock_settings,
        ):
            mock_settings.gemini_api_key = "test-key"
            mock_settings.pipeline_version = "6"
            await run_pipeline(
                docs_path=docs, data_path=data, full=True, db=mock_db, source=_vue_source()
            )

        # With --full, Jina should have been called (file was re-processed)
        mock_jina.embed_batched.assert_called()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_run_help(self):
        from typer.testing import CliRunner

        from vue_docs_ingestion.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0

    def test_status_help(self):
        from typer.testing import CliRunner

        from vue_docs_ingestion.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    def test_run_fails_on_nonexistent_docs_path(self, tmp_path):
        from typer.testing import CliRunner

        from vue_docs_ingestion.cli import app

        runner = CliRunner()
        mock_db = _mock_db()
        with patch("vue_docs_ingestion.cli._get_db", return_value=mock_db):
            result = runner.invoke(app, ["run", "--docs-path", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0

    def test_run_dry_run_lists_files(self, tmp_path):
        from typer.testing import CliRunner

        from vue_docs_ingestion.cli import app

        docs = tmp_path / "src"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\nContent.")
        data = tmp_path / "data"
        data.mkdir()

        mock_db = _mock_db()
        runner = CliRunner()
        with patch("vue_docs_ingestion.cli._get_db", return_value=mock_db):
            result = runner.invoke(
                app,
                ["run", "--docs-path", str(docs), "--data-path", str(data), "--dry-run"],
            )
        assert result.exit_code == 0
        assert "guide.md" in result.output
