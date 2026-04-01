"""Tests for Nuxt adapter and entity extractor."""

from pathlib import Path

import pytest

from vue_docs_core.models.entity import EntityType
from vue_docs_core.parsing.adapters.nuxt import NuxtAdapter
from vue_docs_core.parsing.extractors.nuxt import NuxtEntityExtractor

_adapter = NuxtAdapter()
_extractor = NuxtEntityExtractor()

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "nuxt" / "docs"

needs_nuxt_docs = pytest.mark.skipif(not DOCS_ROOT.exists(), reason="Nuxt docs not cloned")


# ===================================================================
# Content Cleaning
# ===================================================================


class TestNuxtCleanContent:
    def test_read_more_stripped(self):
        raw = 'Some text\n::read-more{title="Guide" to="/docs/guide"}\nMore text'
        result = _adapter.clean_content(raw)
        assert "read-more" not in result
        assert "Some text" in result
        assert "More text" in result

    def test_video_accordion_stripped(self):
        raw = 'Before\n  :video-accordion{title="Watch" videoId="abc123"}\nAfter'
        result = _adapter.clean_content(raw)
        assert "video-accordion" not in result
        assert "After" in result

    def test_link_example_stripped(self):
        raw = 'Text\n::link-example{to="/docs/examples/fetch"}\nMore'
        result = _adapter.clean_content(raw)
        assert "link-example" not in result

    def test_note_block_preserved(self):
        raw = "::note\nThis is important info.\n::\n\nMore text"
        result = _adapter.clean_content(raw)
        assert "::note" in result
        assert "important info" in result

    def test_tip_block_preserved(self):
        raw = "::tip\nHelpful hint here.\n::"
        result = _adapter.clean_content(raw)
        assert "::tip" in result
        assert "Helpful hint" in result

    def test_warning_block_preserved(self):
        raw = "::warning\nBe careful!\n::"
        result = _adapter.clean_content(raw)
        assert "::warning" in result


# ===================================================================
# File Discovery
# ===================================================================


class TestNuxtDiscoverFiles:
    @needs_nuxt_docs
    def test_includes_getting_started(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        getting_started = [p for p in paths if "getting-started" in p]
        assert len(getting_started) > 0

    @needs_nuxt_docs
    def test_includes_api_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        api_files = [p for p in paths if p.startswith("4.api/")]
        assert len(api_files) > 0

    @needs_nuxt_docs
    def test_includes_guide_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        guide_files = [p for p in paths if p.startswith("3.guide/")]
        assert len(guide_files) > 0

    @needs_nuxt_docs
    def test_includes_migration(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        migration = [p for p in paths if "migration" in p]
        assert len(migration) > 0

    @needs_nuxt_docs
    def test_includes_bridge(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        bridge = [p for p in paths if "bridge" in p]
        assert len(bridge) > 0

    @needs_nuxt_docs
    def test_excludes_community(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        community = [p for p in paths if p.startswith("5.community/")]
        assert len(community) == 0


# ===================================================================
# Entity Extraction
# ===================================================================


class TestNuxtEntityExtractor:
    @needs_nuxt_docs
    def test_seed_list_entities(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert "useFetch" in dictionary
        assert "useAsyncData" in dictionary
        assert "NuxtLink" in dictionary
        assert "navigateTo" in dictionary
        assert "defineNuxtConfig" in dictionary

    @needs_nuxt_docs
    def test_classification_composable(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["useFetch"].entity_type == EntityType.COMPOSABLE
        assert dictionary["useHead"].entity_type == EntityType.COMPOSABLE

    @needs_nuxt_docs
    def test_classification_component(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["NuxtLink"].entity_type == EntityType.COMPONENT
        assert dictionary["NuxtPage"].entity_type == EntityType.COMPONENT

    @needs_nuxt_docs
    def test_classification_global_api(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["navigateTo"].entity_type == EntityType.GLOBAL_API
        assert dictionary["defineNuxtPlugin"].entity_type == EntityType.GLOBAL_API

    def test_classify_standalone(self):
        assert _extractor._classify("useSomething") == EntityType.COMPOSABLE
        assert _extractor._classify("NuxtSomething") == EntityType.COMPONENT
        assert _extractor._classify("defineSomething") == EntityType.GLOBAL_API
        assert _extractor._classify("onBeforeSomething") == EntityType.LIFECYCLE_HOOK


# ===================================================================
# Import Patterns
# ===================================================================


class TestNuxtImportPatterns:
    def test_matches_app_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { useFetch } from '#app'"
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)

    def test_matches_imports_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { useState } from '#imports'"
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)

    def test_does_not_match_vue(self):
        patterns = _extractor.get_import_patterns()
        text = "import { ref } from 'vue'"
        matches = [p.search(text) for p in patterns]
        assert all(m is None for m in matches)


# ===================================================================
# Sort Keys
# ===================================================================


class TestNuxtSortKeys:
    @needs_nuxt_docs
    def test_parses_sort_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        assert len(sort_keys) > 0

    @needs_nuxt_docs
    def test_getting_started_before_api(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        gs_keys = {k: v for k, v in sort_keys.items() if "getting-started" in k}
        api_keys = {k: v for k, v in sort_keys.items() if k.startswith("api")}
        if gs_keys and api_keys:
            max_gs = max(gs_keys.values())
            min_api = min(api_keys.values())
            assert max_gs < min_api

    @needs_nuxt_docs
    def test_numeric_prefixes_stripped_from_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        # No key should start with a digit (numeric prefixes stripped)
        for key in sort_keys:
            assert not key[0].isdigit(), f"Key still has numeric prefix: {key}"
