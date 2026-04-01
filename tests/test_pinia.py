"""Tests for Pinia adapter and entity extractor."""

from pathlib import Path

import pytest

from vue_docs_core.models.entity import EntityType
from vue_docs_core.parsing.adapters.pinia import PiniaAdapter
from vue_docs_core.parsing.extractors.pinia import PiniaEntityExtractor

_adapter = PiniaAdapter()
_extractor = PiniaEntityExtractor()

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "pinia" / "packages" / "docs"

needs_pinia_docs = pytest.mark.skipif(not DOCS_ROOT.exists(), reason="Pinia docs not cloned")


class TestPiniaCleanContent:
    def test_rulekit_link_stripped(self):
        raw = 'Text\n<RuleKitLink href="url">Watch</RuleKitLink>\nMore'
        result = _adapter.clean_content(raw)
        assert "RuleKitLink" not in result
        assert "Text" in result

    def test_mastering_pinia_link_stripped(self):
        raw = 'Before\n<MasteringPiniaLink href="url">Learn</MasteringPiniaLink>\nAfter'
        result = _adapter.clean_content(raw)
        assert "MasteringPiniaLink" not in result

    def test_vue_school_link_stripped(self):
        raw = 'Text\n<VueSchoolLink href="url" />\nMore'
        result = _adapter.clean_content(raw)
        assert "VueSchoolLink" not in result

    def test_script_setup_stripped(self):
        raw = "# Title\n\n<script setup>\nimport data from './data'\n</script>\n\nContent"
        result = _adapter.clean_content(raw)
        assert "<script setup>" not in result
        assert "Content" in result

    def test_code_fence_content_preserved(self):
        raw = "```vue\n<script setup>\nconst store = useStore()\n</script>\n```"
        result = _adapter.clean_content(raw)
        assert "<script setup>" in result


class TestPiniaDiscoverFiles:
    @needs_pinia_docs
    def test_includes_core_concepts(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "core-concepts/index.md" in paths
        assert "core-concepts/state.md" in paths

    @needs_pinia_docs
    def test_includes_cookbook(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        cookbook = [p for p in paths if p.startswith("cookbook/")]
        assert len(cookbook) > 0

    @needs_pinia_docs
    def test_includes_ssr(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        assert "ssr/index.md" in paths

    @needs_pinia_docs
    def test_excludes_zh(self):
        files = _adapter.discover_files(DOCS_ROOT)
        paths = {str(f.relative_to(DOCS_ROOT)) for f in files}
        zh_files = [p for p in paths if p.startswith("zh/")]
        assert len(zh_files) == 0


class TestPiniaEntityExtractor:
    @needs_pinia_docs
    def test_seed_list_entities(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert "defineStore" in dictionary
        assert "createPinia" in dictionary
        assert "storeToRefs" in dictionary
        assert "$patch" in dictionary
        assert "mapState" in dictionary

    @needs_pinia_docs
    def test_classification_global_api(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["defineStore"].entity_type == EntityType.GLOBAL_API
        assert dictionary["createPinia"].entity_type == EntityType.GLOBAL_API
        assert dictionary["mapActions"].entity_type == EntityType.GLOBAL_API

    @needs_pinia_docs
    def test_classification_instance_method(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["$patch"].entity_type == EntityType.INSTANCE_METHOD
        assert dictionary["$subscribe"].entity_type == EntityType.INSTANCE_METHOD

    @needs_pinia_docs
    def test_classification_composable(self):
        dictionary = _extractor.build_dictionary(DOCS_ROOT)
        assert dictionary["storeToRefs"].entity_type == EntityType.COMPOSABLE

    def test_classify_standalone(self):
        assert _extractor._classify("$something") == EntityType.INSTANCE_METHOD
        assert _extractor._classify("createSomething") == EntityType.GLOBAL_API
        assert _extractor._classify("useSomething") == EntityType.COMPOSABLE
        assert _extractor._classify("MyComponent") == EntityType.COMPONENT


class TestPiniaImportPatterns:
    def test_matches_pinia_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { defineStore } from 'pinia'"
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)

    def test_matches_testing_import(self):
        patterns = _extractor.get_import_patterns()
        text = "import { createTestingPinia } from '@pinia/testing'"
        matches = [p.search(text) for p in patterns]
        assert any(m is not None for m in matches)

    def test_does_not_match_vue(self):
        patterns = _extractor.get_import_patterns()
        text = "import { ref } from 'vue'"
        matches = [p.search(text) for p in patterns]
        assert all(m is None for m in matches)


class TestPiniaSortKeys:
    @needs_pinia_docs
    def test_parses_sidebar(self):
        repo_root = DOCS_ROOT.parent.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        assert len(sort_keys) > 0

    @needs_pinia_docs
    def test_core_concepts_have_sort_keys(self):
        repo_root = DOCS_ROOT.parent.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        cc_keys = {k: v for k, v in sort_keys.items() if k.startswith("core-concepts")}
        assert len(cc_keys) > 0

    @needs_pinia_docs
    def test_cookbook_has_sort_keys(self):
        repo_root = DOCS_ROOT.parent.parent
        sort_keys = _adapter.parse_sort_keys(repo_root)
        cookbook_keys = {k: v for k, v in sort_keys.items() if k.startswith("cookbook")}
        assert len(cookbook_keys) > 0
