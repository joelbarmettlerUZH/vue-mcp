"""Tests for entity extraction, cross-references, and sort keys."""

from pathlib import Path

import pytest

from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType
from vue_docs_core.models.crossref import CrossRefType
from vue_docs_core.models.entity import EntityType
from vue_docs_core.parsing.crossrefs import (
    _classify_ref_type,
    _resolve_target_path,
    build_crossref_graph,
    extract_cross_references,
)
from vue_docs_core.parsing.entities import (
    _clean_api_name,
    _split_compound_heading,
    build_api_dictionary,
    extract_entities_from_chunk,
    load_dictionary,
    save_dictionary,
)
from vue_docs_core.parsing.markdown import parse_markdown_file
from vue_docs_core.parsing.sort_keys import compute_sort_key, parse_sidebar_config

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "vue-docs" / "src"
API_DIR = DOCS_ROOT / "api"
CONFIG_PATH = DOCS_ROOT.parent / ".vitepress" / "config.ts"

needs_vue_docs = pytest.mark.skipif(
    not DOCS_ROOT.exists(), reason="Vue docs not cloned (run make bootstrap)"
)


# ===================================================================
# Entity Extraction
# ===================================================================


class TestCleanApiName:
    def test_simple_function(self):
        assert _clean_api_name("ref() {#ref}") == "ref"

    def test_dotted_name(self):
        assert _clean_api_name("app.mount() {#app-mount}") == "app.mount"

    def test_component(self):
        assert _clean_api_name("`<Transition>` {#transition}") == "Transition"

    def test_directive(self):
        assert _clean_api_name("v-model {#v-model}") == "v-model"

    def test_instance_property(self):
        assert _clean_api_name("$refs {#refs}") == "$refs"

    def test_sup_tag_stripped(self):
        name = _clean_api_name(
            'app.onUnmount() <sup class="vt-badge" data-text="3.5+" /> {#app-onunmount}'
        )
        assert name == "app.onUnmount"

    def test_self_closing_sup(self):
        name = _clean_api_name(
            'defineSlots()<sup class="vt-badge ts"/> {#defineslots}',
            strict=True,
        )
        assert name == "defineSlots"

    def test_prose_heading_rejected(self):
        assert _clean_api_name("Basic Syntax {#basic-syntax}") is None

    def test_prose_heading_rejected_strict(self):
        assert _clean_api_name("Reactivity {#reactivity}", strict=True) is None

    def test_generic_type(self):
        assert _clean_api_name("PropType\\<T> {#proptype}") == "PropType"

    def test_compile_flag(self):
        name = _clean_api_name("__VUE_OPTIONS_API__ {#vue-options-api}")
        assert name == "__VUE_OPTIONS_API__"


class TestSplitCompoundHeading:
    def test_single(self):
        assert _split_compound_heading("ref() {#ref}") == ["ref"]

    def test_compound(self):
        names = _split_compound_heading(
            "defineProps() & defineEmits() {#defineprops-defineemits}",
            strict=True,
        )
        assert "defineProps" in names
        assert "defineEmits" in names

    def test_backtick_compound(self):
        names = _split_compound_heading(
            "`useSlots()` & `useAttrs()` {#useslots-useattrs}",
            strict=True,
        )
        assert "useSlots" in names
        assert "useAttrs" in names


@needs_vue_docs
class TestBuildApiDictionary:
    @pytest.fixture(scope="class")
    def dictionary(self):
        return build_api_dictionary(API_DIR)

    def test_dictionary_size(self, dictionary):
        assert 150 <= len(dictionary) <= 250

    def test_ref_is_composable(self, dictionary):
        assert "ref" in dictionary
        assert dictionary["ref"].entity_type == EntityType.COMPOSABLE

    def test_v_model_is_directive(self, dictionary):
        assert "v-model" in dictionary
        assert dictionary["v-model"].entity_type == EntityType.DIRECTIVE

    def test_onMounted_is_lifecycle(self, dictionary):
        assert "onMounted" in dictionary
        assert dictionary["onMounted"].entity_type == EntityType.LIFECYCLE_HOOK

    def test_transition_is_component(self, dictionary):
        assert "Transition" in dictionary
        assert dictionary["Transition"].entity_type == EntityType.COMPONENT

    def test_defineProps_is_compiler_macro(self, dictionary):
        assert "defineProps" in dictionary
        assert dictionary["defineProps"].entity_type == EntityType.COMPILER_MACRO

    def test_dollar_refs_is_instance_property(self, dictionary):
        assert "$refs" in dictionary
        assert dictionary["$refs"].entity_type == EntityType.INSTANCE_PROPERTY

    def test_no_prose_headings(self, dictionary):
        prose = ["Basic Syntax", "Reactivity", "Restrictions", "Overview", "Comments"]
        for p in prose:
            assert p not in dictionary, f"Prose heading '{p}' should not be in dictionary"

    def test_page_path_set(self, dictionary):
        assert dictionary["ref"].page_path == "api/reactivity-core.md"


@needs_vue_docs
class TestExtractEntitiesFromChunk:
    @pytest.fixture(scope="class")
    def dictionary(self):
        return build_api_dictionary(API_DIR)

    def test_inline_code_extraction(self, dictionary):
        chunk = Chunk(
            chunk_id="test",
            chunk_type=ChunkType.SECTION,
            content="Use `ref` and `computed` for reactive state.",
            metadata=ChunkMetadata(
                file_path="guide/test.md",
                folder_path="guide",
                page_title="Test",
            ),
        )
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "ref" in entities
        assert "computed" in entities

    def test_import_extraction(self, dictionary):
        chunk = Chunk(
            chunk_id="test-code",
            chunk_type=ChunkType.CODE_BLOCK,
            content="import { ref, reactive, onMounted } from 'vue'",
            metadata=ChunkMetadata(
                file_path="guide/test.md",
                folder_path="guide",
                page_title="Test",
            ),
        )
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "ref" in entities
        assert "reactive" in entities
        assert "onMounted" in entities

    def test_directive_extraction(self, dictionary):
        chunk = Chunk(
            chunk_id="test-tmpl",
            chunk_type=ChunkType.CODE_BLOCK,
            content='<input v-model="name" v-if="show" />',
            metadata=ChunkMetadata(
                file_path="guide/test.md",
                folder_path="guide",
                page_title="Test",
            ),
        )
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "v-model" in entities
        assert "v-if" in entities

    def test_real_computed_md(self, dictionary):
        chunks = parse_markdown_file(DOCS_ROOT / "guide/essentials/computed.md", DOCS_ROOT)
        all_entities: set[str] = set()
        for chunk in chunks:
            all_entities.update(extract_entities_from_chunk(chunk, dictionary))
        assert "computed" in all_entities
        assert "reactive" in all_entities


@needs_vue_docs
class TestSavLoadDictionary:
    def test_round_trip(self, tmp_path):
        d = build_api_dictionary(API_DIR)
        path = tmp_path / "dict.json"
        save_dictionary(d, path)
        loaded = load_dictionary(path)
        assert len(loaded) == len(d)
        assert loaded["ref"].entity_type == d["ref"].entity_type


# ===================================================================
# Cross-References
# ===================================================================


class TestResolveTargetPath:
    def test_absolute_path(self):
        assert (
            _resolve_target_path("/guide/essentials/computed", "api/core.md")
            == "guide/essentials/computed"
        )

    def test_relative_path(self):
        assert (
            _resolve_target_path("./watchers", "guide/essentials/computed.md")
            == "guide/essentials/watchers"
        )

    def test_parent_relative(self):
        assert (
            _resolve_target_path("../components/props", "guide/essentials/computed.md")
            == "guide/components/props"
        )

    def test_strip_html_extension(self):
        assert _resolve_target_path("/guide/computed.html", "api/core.md") == "guide/computed"

    def test_preserve_anchor(self):
        assert (
            _resolve_target_path("/api/reactivity-core#ref", "guide/test.md")
            == "api/reactivity-core#ref"
        )

    def test_no_anchor(self):
        assert (
            _resolve_target_path("/api/reactivity-core", "guide/test.md") == "api/reactivity-core"
        )

    def test_skip_external(self):
        assert _resolve_target_path("https://vuejs.org", "guide/test.md") is None

    def test_skip_same_page_anchor(self):
        assert _resolve_target_path("#some-anchor", "guide/test.md") is None


class TestClassifyRefType:
    def test_guide_to_api_is_high(self):
        assert (
            _classify_ref_type("guide/essentials/computed.md", "api/reactivity-core")
            == CrossRefType.HIGH
        )

    def test_api_to_guide_is_high(self):
        assert (
            _classify_ref_type("api/reactivity-core.md", "guide/essentials/computed")
            == CrossRefType.HIGH
        )

    def test_same_folder_is_medium(self):
        assert (
            _classify_ref_type("guide/essentials/computed.md", "guide/essentials/watchers")
            == CrossRefType.MEDIUM
        )

    def test_cross_folder_is_low(self):
        assert (
            _classify_ref_type("guide/essentials/computed.md", "guide/components/props")
            == CrossRefType.LOW
        )


@needs_vue_docs
class TestExtractCrossReferences:
    def test_lifecycle_md_has_high_refs(self):
        chunks = parse_markdown_file(DOCS_ROOT / "guide/essentials/lifecycle.md", DOCS_ROOT)
        all_refs = []
        for chunk in chunks:
            all_refs.extend(extract_cross_references(chunk))

        high_refs = [r for r in all_refs if r.ref_type == CrossRefType.HIGH]
        assert len(high_refs) >= 2  # guide → api links
        targets = {r.target_path for r in high_refs}
        assert any("composition-api-lifecycle" in t for t in targets)

    def test_computed_md_cross_refs(self):
        chunks = parse_markdown_file(DOCS_ROOT / "guide/essentials/computed.md", DOCS_ROOT)
        all_refs = []
        for chunk in chunks:
            all_refs.extend(extract_cross_references(chunk))

        assert len(all_refs) >= 2
        targets = {r.target_path for r in all_refs}
        assert any("watchers" in t for t in targets)


@needs_vue_docs
class TestBuildCrossrefGraph:
    def test_graph_structure(self):
        chunks = parse_markdown_file(DOCS_ROOT / "guide/essentials/computed.md", DOCS_ROOT)
        graph = build_crossref_graph(chunks)
        assert len(graph) >= 1
        # Check that chunk metadata was updated
        for chunk in chunks:
            if chunk.chunk_id in graph:
                assert len(chunk.metadata.cross_references) > 0


# ===================================================================
# Sort Keys
# ===================================================================


@needs_vue_docs
class TestParseSidebarConfig:
    @pytest.fixture(scope="class")
    def sidebar_map(self):
        return parse_sidebar_config(CONFIG_PATH)

    def test_has_entries(self, sidebar_map):
        assert len(sidebar_map) >= 50

    def test_guide_introduction_first(self, sidebar_map):
        assert sidebar_map["guide/introduction"] == "00_00_00"

    def test_computed_ordering(self, sidebar_map):
        assert sidebar_map["guide/essentials/computed"] == "00_01_03"

    def test_api_section(self, sidebar_map):
        assert sidebar_map["api/application"].startswith("01_")

    def test_guide_before_api(self, sidebar_map):
        assert sidebar_map["guide/introduction"] < sidebar_map["api/application"]

    def test_essentials_ordering(self, sidebar_map):
        essentials = [
            "guide/essentials/application",
            "guide/essentials/template-syntax",
            "guide/essentials/reactivity-fundamentals",
            "guide/essentials/computed",
        ]
        keys = [sidebar_map[p] for p in essentials]
        assert keys == sorted(keys)


@needs_vue_docs
class TestComputeSortKey:
    @pytest.fixture(scope="class")
    def sidebar_map(self):
        return parse_sidebar_config(CONFIG_PATH)

    def test_known_file(self, sidebar_map):
        key = compute_sort_key("guide/essentials/computed.md", sidebar_map)
        assert key == "00_01_03"

    def test_unknown_file_fallback(self, sidebar_map):
        key = compute_sort_key("tutorial/step-1.md", sidebar_map)
        assert key.startswith("99_")

    def test_fallback_preserves_path(self, sidebar_map):
        key = compute_sort_key("tutorial/step-1.md", sidebar_map)
        assert key == "99_tutorial/step-1"
