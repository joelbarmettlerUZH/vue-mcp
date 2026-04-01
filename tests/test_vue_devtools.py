"""Tests for Vue DevTools adapter and entity extractor."""

from pathlib import Path

import pytest

from vue_docs_core.models.entity import EntityType
from vue_docs_core.parsing.adapters.vue_devtools import VueDevToolsAdapter
from vue_docs_core.parsing.extractors.vue_devtools import VueDevToolsEntityExtractor

_adapter = VueDevToolsAdapter()
_extractor = VueDevToolsEntityExtractor()

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "vue-devtools" / "docs"

needs_docs = pytest.mark.skipif(not DOCS_ROOT.exists(), reason="Vue DevTools docs not cloned")


class TestVueDevToolsCleanContent:
    def test_home_component_stripped(self):
        raw = "---\nlayout: home\n---\n\n<Home />\n"
        result = _adapter.clean_content(raw)
        assert "<Home" not in result

    def test_use_mode_list_stripped(self):
        raw = "Some text\n<UseModeList />\nMore text"
        result = _adapter.clean_content(raw)
        assert "UseModeList" not in result
        assert "Some text" in result

    def test_regular_content_preserved(self):
        raw = "# Title\n\nSome content here.\n\n```js\nconsole.log('hello')\n```"
        result = _adapter.clean_content(raw)
        assert "# Title" in result
        assert "console.log" in result


class TestVueDevToolsDiscoverFiles:
    @needs_docs
    def test_includes_getting_started(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "getting-started/introduction.md" in paths

    @needs_docs
    def test_includes_plugins(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "plugins/api.md" in paths

    @needs_docs
    def test_includes_guide(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        guide_files = [p for p in paths if p.startswith("guide/")]
        assert len(guide_files) > 0

    @needs_docs
    def test_excludes_root_index(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "index.md" not in paths

    @needs_docs
    def test_file_count(self):
        files = _adapter.discover_files(DOCS_ROOT)
        assert len(files) == 12  # 13 total minus root index.md


class TestVueDevToolsEntityExtractor:
    @needs_docs
    def test_seed_list_entities(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert "addCustomTab" in dictionary
        assert "addCustomCommand" in dictionary
        assert "onDevToolsClientConnected" in dictionary

    @needs_docs
    def test_classification(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["addCustomTab"].entity_type == EntityType.GLOBAL_API
        assert dictionary["onDevToolsClientConnected"].entity_type == EntityType.LIFECYCLE_HOOK

    def test_classify_standalone(self):
        assert _extractor._classify("addSomething") == EntityType.GLOBAL_API
        assert _extractor._classify("onSomething") == EntityType.LIFECYCLE_HOOK
        assert _extractor._classify("MyComponent") == EntityType.COMPONENT


class TestVueDevToolsImportPatterns:
    def test_matches_devtools_api(self):
        patterns = _extractor.get_import_patterns()
        text = "import { addCustomTab } from '@vue/devtools-api'"
        assert any(p.search(text) for p in patterns)

    def test_does_not_match_vue(self):
        patterns = _extractor.get_import_patterns()
        text = "import { ref } from 'vue'"
        assert all(p.search(text) is None for p in patterns)


class TestVueDevToolsSortKeys:
    @needs_docs
    def test_parses_sidebar(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        assert len(sort_keys) > 0

    @needs_docs
    def test_getting_started_has_sort_keys(self):
        repo_root = DOCS_ROOT.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        gs_keys = {k: v for k, v in sort_keys.items() if k.startswith("getting-started")}
        assert len(gs_keys) > 0
