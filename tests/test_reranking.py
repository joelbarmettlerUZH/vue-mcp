"""Tests for Day 11 — Jina reranker integration in the search pipeline.

Covers the _rerank_hits function: normal reranking, graceful fallback on
failure, empty input, and score replacement.
"""

from unittest.mock import AsyncMock, patch

import pytest

from vue_docs_core.clients.jina import JinaClient, RerankResult
from vue_docs_core.clients.qdrant import SearchHit
from vue_docs_server.tools.search import _rerank_hits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hit(
    chunk_id: str = "guide/essentials/computed#section",
    score: float = 0.5,
    content: str = "Some documentation content.",
    breadcrumb: str = "Guide > Essentials > Computed",
    chunk_type: str = "section",
    preceding_prose: str = "",
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        payload={
            "chunk_id": chunk_id,
            "content": content,
            "breadcrumb": breadcrumb,
            "chunk_type": chunk_type,
            "preceding_prose": preceding_prose,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRerankHits:
    @pytest.mark.asyncio
    async def test_reranking_reorders_by_reranker_score(self):
        """Hits should be reordered based on the reranker's scores, not fusion scores."""
        hits = [
            _make_hit(chunk_id="chunk-a", score=0.9, content="First by fusion"),
            _make_hit(chunk_id="chunk-b", score=0.7, content="Second by fusion"),
            _make_hit(chunk_id="chunk-c", score=0.5, content="Third by fusion"),
        ]

        # Reranker says chunk-c is best, then chunk-a, then chunk-b
        fake_rerank = RerankResult(
            indices=[2, 0, 1],
            scores=[0.95, 0.80, 0.30],
            total_tokens=500,
        )

        jina = JinaClient(api_key="test")
        with patch.object(jina, "rerank", new=AsyncMock(return_value=fake_rerank)):
            result = await _rerank_hits(jina, "test query", hits)

        assert len(result) == 3
        assert result[0].chunk_id == "chunk-c"
        assert result[1].chunk_id == "chunk-a"
        assert result[2].chunk_id == "chunk-b"

    @pytest.mark.asyncio
    async def test_reranking_replaces_scores_with_reranker_scores(self):
        """Scores on returned hits should come from the reranker, not the original fusion."""
        hits = [
            _make_hit(chunk_id="chunk-a", score=0.9),
            _make_hit(chunk_id="chunk-b", score=0.7),
        ]

        fake_rerank = RerankResult(
            indices=[1, 0],
            scores=[0.99, 0.10],
            total_tokens=200,
        )

        jina = JinaClient(api_key="test")
        with patch.object(jina, "rerank", new=AsyncMock(return_value=fake_rerank)):
            result = await _rerank_hits(jina, "query", hits)

        assert result[0].score == pytest.approx(0.99)
        assert result[1].score == pytest.approx(0.10)

    @pytest.mark.asyncio
    async def test_reranking_empty_hits_returns_empty(self):
        """Empty input should be returned immediately without calling the reranker."""
        jina = JinaClient(api_key="test")
        mock_rerank = AsyncMock()
        with patch.object(jina, "rerank", new=mock_rerank):
            result = await _rerank_hits(jina, "query", [])

        assert result == []
        mock_rerank.assert_not_called()

    @pytest.mark.asyncio
    async def test_reranking_falls_back_on_api_error(self):
        """If the reranker API fails, fall back to original ordering trimmed to _RERANK_TOP_N."""
        hits = [_make_hit(chunk_id=f"chunk-{i}", score=1.0 - i * 0.1) for i in range(5)]

        jina = JinaClient(api_key="test")
        with patch.object(jina, "rerank", new=AsyncMock(side_effect=RuntimeError("API down"))):
            result = await _rerank_hits(jina, "query", hits)

        # Should fall back to original hits, trimmed
        assert len(result) == 5
        assert result[0].chunk_id == "chunk-0"

    @pytest.mark.asyncio
    async def test_reranking_includes_breadcrumb_in_document_text(self):
        """The document text sent to the reranker should include the breadcrumb for context."""
        hits = [_make_hit(
            content="Computed properties cache their results.",
            breadcrumb="Guide > Essentials > Computed",
        )]

        captured_docs = []

        async def fake_rerank(query, documents):
            captured_docs.extend(documents)
            return RerankResult(indices=[0], scores=[0.9], total_tokens=100)

        jina = JinaClient(api_key="test")
        with patch.object(jina, "rerank", side_effect=fake_rerank):
            await _rerank_hits(jina, "query", hits)

        assert "Guide > Essentials > Computed" in captured_docs[0]
        assert "Computed properties cache their results." in captured_docs[0]

    @pytest.mark.asyncio
    async def test_reranking_code_block_includes_preceding_prose(self):
        """Code block chunks should include preceding_prose in the reranker document text."""
        hits = [_make_hit(
            chunk_type="code_block",
            content="const count = ref(0)",
            preceding_prose="Here is an example of using ref:",
            breadcrumb="Guide > Essentials > Reactivity",
        )]

        captured_docs = []

        async def fake_rerank(query, documents):
            captured_docs.extend(documents)
            return RerankResult(indices=[0], scores=[0.9], total_tokens=100)

        jina = JinaClient(api_key="test")
        with patch.object(jina, "rerank", side_effect=fake_rerank):
            await _rerank_hits(jina, "query", hits)

        doc = captured_docs[0]
        assert "Here is an example of using ref:" in doc
        assert "const count = ref(0)" in doc

    @pytest.mark.asyncio
    async def test_reranking_sends_all_candidates(self):
        """All hits should be sent to the reranker."""
        hits = [_make_hit(chunk_id=f"chunk-{i}", score=1.0 - i * 0.01) for i in range(30)]

        captured_docs = []

        async def fake_rerank(query, documents):
            captured_docs.extend(documents)
            n = len(documents)
            return RerankResult(
                indices=list(range(n)),
                scores=[1.0 - i * 0.03 for i in range(n)],
                total_tokens=1000,
            )

        jina = JinaClient(api_key="test")
        with patch.object(jina, "rerank", side_effect=fake_rerank):
            result = await _rerank_hits(jina, "query", hits)

        assert len(captured_docs) == 30
        assert len(result) == 30
