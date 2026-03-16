"""Tests for Day 12 — Cross-reference expansion logic.

Covers expand_cross_references: targeted vs page-level expansion,
priority cutoffs, deduplication, empty inputs, and target capping.
"""

from unittest.mock import MagicMock, call

import pytest

from vue_docs_core.clients.qdrant import QdrantDocClient, SearchHit
from vue_docs_core.models.crossref import CrossRefType
from vue_docs_core.retrieval.expansion import (
    expand_cross_references,
    _EXPANSION_SCORE,
    _LOW_CUTOFF,
    _MAX_TARGETS,
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


def _make_payload(
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
    def test_targeted_expansion_uses_chunk_id_lookup(self):
        """Cross-refs with anchors should fetch by chunk_id, not file_path."""
        hits = [
            _make_hit(
                chunk_id="guide/components/v-model#basic-usage",
                score=0.9,
                cross_references=["api/sfc-script-setup#definemodel"],
            ),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = [
            _make_payload("api/sfc-script-setup#definemodel"),
        ]

        result = expand_cross_references(hits, qdrant)

        assert len(result) == 2
        assert result[1].chunk_id == "api/sfc-script-setup#definemodel"
        assert result[1].score == _EXPANSION_SCORE
        qdrant.get_by_chunk_ids.assert_called_once_with(["api/sfc-script-setup#definemodel"])
        qdrant.get_by_file_paths.assert_not_called()

    def test_page_level_expansion_uses_file_path_lookup(self):
        """Cross-refs without anchors should fetch by file_path."""
        hits = [
            _make_hit(
                cross_references=["guide/essentials/forms"],
            ),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = []
        qdrant.get_by_file_paths.return_value = [
            _make_payload("guide/essentials/forms#basic-usage"),
        ]

        result = expand_cross_references(hits, qdrant)

        assert len(result) == 2
        qdrant.get_by_file_paths.assert_called_once_with(
            file_paths=["guide/essentials/forms.md"],
            chunk_types=["section", "subsection", "page_summary"],
        )

    def test_mixed_targeted_and_page_level(self):
        """Both targeted and page-level refs should be expanded."""
        hits = [
            _make_hit(
                cross_references=[
                    "api/sfc-script-setup#definemodel",  # targeted
                    "guide/essentials/forms",             # page-level
                ],
            ),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = [
            _make_payload("api/sfc-script-setup#definemodel"),
        ]
        qdrant.get_by_file_paths.return_value = [
            _make_payload("guide/essentials/forms#text"),
        ]

        result = expand_cross_references(hits, qdrant)

        assert len(result) == 3
        qdrant.get_by_chunk_ids.assert_called_once()
        qdrant.get_by_file_paths.assert_called_once()

    def test_deduplicates_existing_chunks(self):
        """Chunks already in results should not be added again."""
        hits = [
            _make_hit(
                chunk_id="guide/a#section",
                cross_references=["api/core#ref"],
            ),
            _make_hit(
                chunk_id="api/core#ref",
                score=0.5,
                file_path="api/core.md",
            ),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = [
            _make_payload("api/core#ref"),
        ]

        result = expand_cross_references(hits, qdrant)

        assert len(result) == 2
        assert sum(1 for h in result if h.chunk_id == "api/core#ref") == 1

    def test_no_expansion_without_cross_references(self):
        hits = [_make_hit(cross_references=[])]
        qdrant = MagicMock(spec=QdrantDocClient)

        result = expand_cross_references(hits, qdrant)

        assert len(result) == 1
        qdrant.get_by_chunk_ids.assert_not_called()
        qdrant.get_by_file_paths.assert_not_called()

    def test_empty_hits_returns_empty(self):
        qdrant = MagicMock(spec=QdrantDocClient)
        assert expand_cross_references([], qdrant) == []

    def test_priority_cutoffs_with_crossref_types(self):
        """LOW refs beyond top-5 should be skipped."""
        hits = []
        for i in range(8):
            hits.append(_make_hit(
                chunk_id=f"chunk-{i}#s",
                score=1.0 - i * 0.05,
                cross_references=[f"target/page-{i}#section"],
            ))

        crossref_types = {
            f"chunk-{i}#s": {f"target/page-{i}#section": "low"}
            for i in range(8)
        }

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = []

        expand_cross_references(hits, qdrant, crossref_types=crossref_types)

        call_args = qdrant.get_by_chunk_ids.call_args
        assert len(call_args[0][0]) == _LOW_CUTOFF

    def test_caps_at_max_targets(self):
        """Expansion should not exceed _MAX_TARGETS total."""
        hits = []
        for i in range(20):
            hits.append(_make_hit(
                chunk_id=f"chunk-{i}#s",
                score=1.0 - i * 0.01,
                cross_references=[f"target/page-{i}#section"],
            ))

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = []

        expand_cross_references(hits, qdrant)

        call_args = qdrant.get_by_chunk_ids.call_args
        assert len(call_args[0][0]) == _MAX_TARGETS

    def test_targeted_preferred_over_page_level(self):
        """When capped, targeted refs should be kept over page-level refs."""
        hits = [
            _make_hit(
                chunk_id="a#s",
                score=0.9,
                cross_references=["target#specific-section"],
            ),
            _make_hit(
                chunk_id="b#s",
                score=0.8,
                cross_references=["other/page"],
            ),
        ]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = []
        qdrant.get_by_file_paths.return_value = []

        expand_cross_references(hits, qdrant)

        # Both should be fetched (under cap), but targeted via get_by_chunk_ids
        qdrant.get_by_chunk_ids.assert_called_once_with(["target#specific-section"])
        qdrant.get_by_file_paths.assert_called_once()

    def test_handles_md_extension_in_page_level_target(self):
        """Page-level targets already ending in .md should not get double-suffixed."""
        hits = [_make_hit(cross_references=["guide/intro.md"])]

        qdrant = MagicMock(spec=QdrantDocClient)
        qdrant.get_by_chunk_ids.return_value = []
        qdrant.get_by_file_paths.return_value = []

        expand_cross_references(hits, qdrant)

        call_args = qdrant.get_by_file_paths.call_args
        assert "guide/intro.md" in call_args.kwargs["file_paths"]
