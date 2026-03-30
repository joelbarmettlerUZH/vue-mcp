"""Tests for Vitest adapter and entity extractor."""

from pathlib import Path

import pytest

from vue_docs_core.models.entity import EntityType
from vue_docs_core.parsing.adapters.vitest import VitestAdapter
from vue_docs_core.parsing.extractors.vitest import VitestEntityExtractor

_adapter = VitestAdapter()
_extractor = VitestEntityExtractor()

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "vitest" / "docs"

needs_vitest_docs = pytest.mark.skipif(not DOCS_ROOT.exists(), reason="Vitest docs not cloned")


# ===================================================================
# Content Cleaning
# ===================================================================


class TestVitestCleanContent:
    def test_version_tag_block_stripped(self):
        raw = "Some text\n<Version>4.1.0</Version>\nMore text"
        result = _adapter.clean_content(raw)
        assert "Version" not in result
        assert "4.1.0" not in result
        assert "Some text" in result

    def test_version_tag_self_closing_stripped(self):
        raw = 'Before\n<Version type="experimental" />\nAfter'
        result = _adapter.clean_content(raw)
        assert "Version" not in result

    def test_deprecated_stripped(self):
        raw = "API docs\n<Deprecated />\nContent"
        result = _adapter.clean_content(raw)
        assert "Deprecated" not in result
        assert "Content" in result

    def test_experimental_stripped(self):
        raw = "Title\n<Experimental />\nBody"
        result = _adapter.clean_content(raw)
        assert "Experimental" not in result

    def test_croot_stripped(self):
        raw = "Option <CRoot /> description"
        result = _adapter.clean_content(raw)
        assert "CRoot" not in result

    def test_courselink_block_stripped(self):
        raw = 'Text\n<CourseLink href="url">Watch</CourseLink>\nMore'
        result = _adapter.clean_content(raw)
        assert "CourseLink" not in result

    def test_badge_stripped(self):
        raw = 'Text <Badge type="warning">experimental</Badge> more'
        result = _adapter.clean_content(raw)
        assert "Badge" not in result
        assert "Text" in result

    def test_img_theme_stripped(self):
        raw = 'Before\n<img img-light src="/screenshot.png">\n<img img-dark src="/screenshot-dark.png">\nAfter'
        result = _adapter.clean_content(raw)
        assert "img-light" not in result
        assert "img-dark" not in result
        assert "After" in result

    def test_script_setup_stripped(self):
        raw = "# Title\n\n<script setup>\nimport { data } from './data'\n</script>\n\nContent"
        result = _adapter.clean_content(raw)
        assert "<script setup>" not in result
        assert "Content" in result

    def test_code_fence_content_preserved(self):
        raw = "```html\n<script setup>\nimport { ref } from 'vue'\n</script>\n```"
        result = _adapter.clean_content(raw)
        assert "<script setup>" in result


# ===================================================================
# File Discovery
# ===================================================================


class TestVitestDiscoverFiles:
    @needs_vitest_docs
    def test_includes_api_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "api/test.md" in paths
        assert "api/vi.md" in paths
        assert "api/expect.md" in paths

    @needs_vitest_docs
    def test_includes_guide_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "guide/index.md" in paths
        assert "guide/mocking.md" in paths

    @needs_vitest_docs
    def test_includes_config_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "config/index.md" in paths
        assert "config/testtimeout.md" in paths

    @needs_vitest_docs
    def test_excludes_blog(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        blog_files = [p for p in paths if p.startswith("blog/")]
        assert len(blog_files) == 0

    @needs_vitest_docs
    def test_excludes_meta_pages(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "team.md" not in paths
        assert "todo.md" not in paths
        assert "blog.md" not in paths
        assert "index.md" not in paths

    @needs_vitest_docs
    def test_excludes_cli_generated(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "guide/cli-generated.md" not in paths

    @needs_vitest_docs
    def test_excludes_guide_examples(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        example_files = [p for p in paths if p.startswith("guide/examples/")]
        assert len(example_files) == 0


# ===================================================================
# Entity Extraction
# ===================================================================


class TestVitestEntityExtractor:
    @needs_vitest_docs
    def test_seed_list_entities(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert "test" in dictionary
        assert "describe" in dictionary
        assert "expect" in dictionary
        assert "vi.mock" in dictionary
        assert "vi.fn" in dictionary
        assert "beforeEach" in dictionary

    @needs_vitest_docs
    def test_classification_global_api(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["test"].entity_type == EntityType.GLOBAL_API
        assert dictionary["describe"].entity_type == EntityType.GLOBAL_API
        assert dictionary["defineConfig"].entity_type == EntityType.GLOBAL_API

    @needs_vitest_docs
    def test_classification_lifecycle_hook(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["beforeEach"].entity_type == EntityType.LIFECYCLE_HOOK
        assert dictionary["afterAll"].entity_type == EntityType.LIFECYCLE_HOOK

    @needs_vitest_docs
    def test_classification_utility(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["vi.mock"].entity_type == EntityType.UTILITY
        assert dictionary["vi.fn"].entity_type == EntityType.UTILITY

    @needs_vitest_docs
    def test_classification_option(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["testTimeout"].entity_type == EntityType.OPTION
        assert dictionary["coverage"].entity_type == EntityType.OPTION

    def test_classify_standalone(self):
        """Test classification without docs (pure pattern matching)."""
        assert _extractor._classify("vi.something") == EntityType.UTILITY
        assert _extractor._classify("test.skip") == EntityType.GLOBAL_API
        assert _extractor._classify("beforeSomething") == EntityType.LIFECYCLE_HOOK
        assert _extractor._classify("MyComponent") == EntityType.COMPONENT


# ===================================================================
# Import Patterns
# ===================================================================


class TestVitestImportPatterns:
    def test_matches_vitest_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { test, expect, vi } from 'vitest'"
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)

    def test_matches_vitest_config_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { defineConfig } from 'vitest/config'"
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)

    def test_does_not_match_vite_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { defineConfig } from 'vite'"
        matches = [p.search(text) for p in patterns]
        assert all(m is None for m in matches)

    def test_matches_double_quotes(self):
        patterns = _extractor.get_import_patterns()
        text = 'import { describe } from "vitest"'
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)


# ===================================================================
# Sort Keys
# ===================================================================


class TestVitestSortKeys:
    @needs_vitest_docs
    def test_parses_sidebar(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        assert len(sort_keys) > 0

    @needs_vitest_docs
    def test_guide_pages_have_sort_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        guide_keys = {k: v for k, v in sort_keys.items() if k.startswith("guide")}
        assert len(guide_keys) > 0

    @needs_vitest_docs
    def test_config_pages_have_sort_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        config_keys = {k: v for k, v in sort_keys.items() if k.startswith("config")}
        assert len(config_keys) > 0

    @needs_vitest_docs
    def test_api_pages_have_sort_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        api_keys = {k: v for k, v in sort_keys.items() if k.startswith("api")}
        assert len(api_keys) > 0
