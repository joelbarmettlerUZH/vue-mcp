"""Tests for Day 12 — Cross-reference expansion logic.

Covers expand_cross_references: basic expansion, priority cutoffs,
deduplication, empty inputs, and no-op when no cross-references exist.
"""

from unittest.mock import MagicMock

import pytest

from vue_docs_core.clients.qdrant import QdrantDocClient, SearchHit
from vue_docs_core.models.crossref import CrossRefType
from vue_docs_core.retrieval.expansion import (
    expand_cross_references,
    _EXPANSION_SCORE,
    _LOW_CUTOFF,
    _MAX_TARGET_PAGES,
    _MEDIUM_CUTOFF,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hit(
    chunk_id: str = "guide/essentials/computed#section",
    score: float = 0.5,
    cross_references: list[str] | None = None,
    file_path: str = "guide/essentials/computed.md",
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        payload={
            "chunk_id": chunk_id,
            "content": "Some content.",
            "file_path": file_path,
            "chunk_type": "section",
            "cross_references": cross_references or [],
        },
    )


def _make_expanded_payload(
    chunk_id: str,
    file_path: str = "api/reactivity-core.md",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "content": "Expanded content.",
        "file_path": file_path,
        "chunk_type": "section",
        "cross_references": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExpandCrossReferences:
    def test_expands_cross_referenced_chunks(self):
        """Chunks from cross-referenced pages should be added to results."""
        hits = [
            _make_hit(
                chunk_id="guide/essentials/computed#caching",
                score=0.9,
                cross_references=["api/reactivity-core"],
            ),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = [
            _make_expanded_payload("api/reactivity-core#computed"),
        ]

        result = expand_cross_references(hits, qdrant)

        assert len(result) == 2
        assert result[0].chunk_id == "guide/essentials/computed#caching"
        assert result[1].chunk_id == "api/reactivity-core#computed"
        assert result[1].score == _EXPANSION_SCORE

    def test_deduplicates_existing_chunks(self):
        """Chunks already in results should not be added again."""
        hits = [
            _make_hit(
                chunk_id="guide/essentials/computed#caching",
                score=0.9,
                cross_references=["api/reactivity-core"],
            ),
            _make_hit(
                chunk_id="api/reactivity-core#computed",
                score=0.5,
                file_path="api/reactivity-core.md",
            ),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = [
            _make_expanded_payload("api/reactivity-core#computed"),
        ]

        result = expand_cross_references(hits, qdrant)

        # Should not add a duplicate
        assert len(result) == 2
        chunk_ids = [h.chunk_id for h in result]
        assert chunk_ids.count("api/reactivity-core#computed") == 1

    def test_no_expansion_without_cross_references(self):
        """Hits without cross-references should not trigger any Qdrant lookups."""
        hits = [_make_hit(cross_references=[])]

        qdrant = MagicMock(spec=QdrantDocClient)
        result = expand_cross_references(hits, qdrant)

        assert len(result) == 1
        qdrant.get_by_file_paths.assert_not_called()

    def test_empty_hits_returns_empty(self):
        qdrant = MagicMock(spec=QdrantDocClient)
        result = expand_cross_references([], qdrant)
        assert result == []

    def test_fetches_section_level_chunks_only(self):
        """Expansion should request only section/subsection chunk types."""
        hits = [
            _make_hit(cross_references=["guide/components/props"]),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = []

        expand_cross_references(hits, qdrant)

        qdrant.get_by_file_paths.assert_called_once_with(
            file_paths=["guide/components/props.md"],
            chunk_types=["section", "subsection"],
        )

    def test_multiple_hits_with_same_target_deduplicates_paths(self):
        """If multiple hits reference the same page, it should be fetched once."""
        hits = [
            _make_hit(chunk_id="a#1", score=0.9, cross_references=["api/core"]),
            _make_hit(chunk_id="b#2", score=0.8, cross_references=["api/core"]),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = [
            _make_expanded_payload("api/core#ref"),
        ]

        result = expand_cross_references(hits, qdrant)

        # Should have called with deduplicated paths
        call_args = qdrant.get_by_file_paths.call_args
        assert len(call_args.kwargs["file_paths"]) == 1

    def test_priority_cutoffs_with_crossref_types(self):
        """LOW refs beyond top-5 and MEDIUM refs beyond top-10 should be skipped."""
        # Create 12 hits — only the first few should expand LOW/MEDIUM refs
        hits = []
        for i in range(12):
            hits.append(_make_hit(
                chunk_id=f"chunk-{i}#s",
                score=1.0 - i * 0.05,
                cross_references=[f"target/page-{i}"],
            ))

        # Provide crossref types: all LOW
        crossref_types = {
            f"chunk-{i}#s": {f"target/page-{i}": "low"}
            for i in range(12)
        }

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = []

        expand_cross_references(hits, qdrant, crossref_types=crossref_types)

        # Only the first _LOW_CUTOFF hits should have their targets expanded
        call_args = qdrant.get_by_file_paths.call_args
        assert len(call_args.kwargs["file_paths"]) == _LOW_CUTOFF

    def test_high_priority_preferred_over_low(self):
        """HIGH priority refs should be kept when capped to _MAX_TARGET_PAGES."""
        hits = [
            # Rank 0: HIGH ref
            _make_hit(chunk_id="chunk-0#s", score=0.9, cross_references=["high-target"]),
            # Rank 1: LOW ref
            _make_hit(chunk_id="chunk-1#s", score=0.8, cross_references=["low-target"]),
        ]

        crossref_types = {
            "chunk-0#s": {"high-target": "high"},
            "chunk-1#s": {"low-target": "low"},
        }

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = []

        expand_cross_references(hits, qdrant, crossref_types=crossref_types)

        call_args = qdrant.get_by_file_paths.call_args
        paths = call_args.kwargs["file_paths"]
        # HIGH should come before LOW
        assert paths.index("high-target.md") < paths.index("low-target.md")

    def test_caps_at_max_target_pages(self):
        """Expansion should not fetch more than _MAX_TARGET_PAGES."""
        hits = []
        for i in range(20):
            hits.append(_make_hit(
                chunk_id=f"chunk-{i}#s",
                score=1.0 - i * 0.05,
                cross_references=[f"target/page-{i}"],
            ))

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = []

        expand_cross_references(hits, qdrant)

        call_args = qdrant.get_by_file_paths.call_args
        assert len(call_args.kwargs["file_paths"]) == _MAX_TARGET_PAGES

    def test_handles_md_extension_in_target_path(self):
        """Target paths already ending in .md should not get double-suffixed."""
        hits = [
            _make_hit(cross_references=["guide/intro.md"]),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_file_paths.return_value = []

        expand_cross_references(hits, qdrant)

        call_args = qdrant.get_by_file_paths.call_args
        assert "guide/intro.md" in call_args.kwargs["file_paths"]
        assert "guide/intro.md.md" not in call_args.kwargs["file_paths"]
