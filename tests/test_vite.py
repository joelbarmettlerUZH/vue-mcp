"""Tests for Vite adapter and entity extractor."""

from pathlib import Path

import pytest

from vue_docs_core.models.entity import EntityType
from vue_docs_core.parsing.adapters.vite import ViteAdapter
from vue_docs_core.parsing.extractors.vite import ViteEntityExtractor

_adapter = ViteAdapter()
_extractor = ViteEntityExtractor()

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "vite" / "docs"

needs_vite_docs = pytest.mark.skipif(
    not DOCS_ROOT.exists(), reason="Vite docs not cloned (run make bootstrap)"
)


# ===================================================================
# Content Cleaning
# ===================================================================


class TestViteCleanContent:
    def test_scrimba_link_block_stripped(self):
        raw = 'Some text\n<ScrimbaLink href="https://example.com" title="Test">Watch</ScrimbaLink>\nMore text'
        result = _adapter.clean_content(raw)
        assert "ScrimbaLink" not in result
        assert "Some text" in result
        assert "More text" in result

    def test_scrimba_link_self_closing_stripped(self):
        raw = 'Before\n<ScrimbaLink href="https://example.com" title="Test" />\nAfter'
        result = _adapter.clean_content(raw)
        assert "ScrimbaLink" not in result
        assert "Before" in result
        assert "After" in result

    def test_audio_element_stripped(self):
        raw = 'Text before\n<audio id="vite-audio">\n  <source src="/vite.mp3" type="audio/mpeg">\n</audio>\nText after'
        result = _adapter.clean_content(raw)
        assert "<audio" not in result
        assert "Text before" in result
        assert "Text after" in result

    def test_script_setup_stripped(self):
        raw = "# Title\n\n<script setup>\nimport { data } from './releases.data'\n</script>\n\nContent here"
        result = _adapter.clean_content(raw)
        assert "<script setup>" not in result
        assert "# Title" in result
        assert "Content here" in result

    def test_prettier_ignore_stripped(self):
        raw = "Some text\n<!-- prettier-ignore -->\n| Column |"
        result = _adapter.clean_content(raw)
        assert "prettier-ignore" not in result
        assert "| Column |" in result

    def test_code_fence_content_preserved(self):
        raw = "```html\n<script setup>\nimport { ref } from 'vue'\n</script>\n```"
        result = _adapter.clean_content(raw)
        # Content inside code fences should NOT be stripped
        assert "<script setup>" in result


# ===================================================================
# File Discovery
# ===================================================================


class TestViteDiscoverFiles:
    @needs_vite_docs
    def test_includes_guide_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "guide/index.md" in paths
        assert "guide/features.md" in paths

    @needs_vite_docs
    def test_includes_config_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "config/shared-options.md" in paths
        assert "config/server-options.md" in paths

    @needs_vite_docs
    def test_includes_changes_files(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "changes/index.md" in paths

    @needs_vite_docs
    def test_excludes_blog(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        blog_files = [p for p in paths if p.startswith("blog/")]
        assert len(blog_files) == 0

    @needs_vite_docs
    def test_excludes_meta_pages(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "team.md" not in paths
        assert "releases.md" not in paths
        assert "acknowledgements.md" not in paths
        assert "live.md" not in paths
        assert "blog.md" not in paths

    @needs_vite_docs
    def test_excludes_root_index(self):
        """Root index.md is a landing page with script setup hero, not doc content."""
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "index.md" not in paths

    @needs_vite_docs
    def test_includes_plugins(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "plugins/index.md" in paths


# ===================================================================
# Entity Extraction
# ===================================================================


class TestViteEntityExtractor:
    @needs_vite_docs
    def test_seed_list_entities(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert "createServer" in dictionary
        assert "defineConfig" in dictionary
        assert "build" in dictionary
        assert "import.meta.hot" in dictionary

    @needs_vite_docs
    def test_classification_global_api(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["createServer"].entity_type == EntityType.GLOBAL_API
        assert dictionary["defineConfig"].entity_type == EntityType.GLOBAL_API

    @needs_vite_docs
    def test_classification_lifecycle_hook(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["configResolved"].entity_type == EntityType.LIFECYCLE_HOOK
        assert dictionary["transform"].entity_type == EntityType.LIFECYCLE_HOOK

    @needs_vite_docs
    def test_classification_option(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["server.port"].entity_type == EntityType.OPTION
        assert dictionary["build.sourcemap"].entity_type == EntityType.OPTION

    @needs_vite_docs
    def test_classification_hmr(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["import.meta.hot.accept"].entity_type == EntityType.INSTANCE_METHOD

    def test_classify_standalone(self):
        """Test classification without docs (pure pattern matching)."""
        assert _extractor._classify("createFoo") == EntityType.GLOBAL_API
        assert _extractor._classify("server.bar") == EntityType.OPTION
        assert _extractor._classify("import.meta.hot.accept") == EntityType.INSTANCE_METHOD
        assert _extractor._classify("MyComponent") == EntityType.COMPONENT


# ===================================================================
# Import Patterns
# ===================================================================


class TestViteImportPatterns:
    def test_matches_vite_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { defineConfig } from 'vite'"
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)
        match = next(m for m in matches if m)
        assert "defineConfig" in match.group(1)

    def test_does_not_match_vitest(self):
        patterns = _extractor.get_import_patterns()
        text = "import { describe } from 'vitest'"
        matches = [p.search(text) for p in patterns]
        assert all(m is None for m in matches)

    def test_matches_double_quotes(self):
        patterns = _extractor.get_import_patterns()
        text = 'import { createServer } from "vite"'
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)


# ===================================================================
# Sort Keys
# ===================================================================


class TestViteSortKeys:
    @needs_vite_docs
    def test_parses_sidebar(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        assert len(sort_keys) > 0

    @needs_vite_docs
    def test_guide_pages_have_sort_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        # Guide index should have a sort key
        guide_keys = {k: v for k, v in sort_keys.items() if k.startswith("guide")}
        assert len(guide_keys) > 0

    @needs_vite_docs
    def test_config_pages_have_sort_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        config_keys = {k: v for k, v in sort_keys.items() if k.startswith("config")}
        assert len(config_keys) > 0
