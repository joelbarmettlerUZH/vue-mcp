"""Tests for MCP server components.

Covers startup state loading, reconstruction formatting, entity detection
in search, the MCP tool registration, api_lookup tool, and end-to-end MCP
protocol integration tests using fastmcp.Client for in-process testing.

No real API calls — Jina, Qdrant, and BM25 are mocked throughout.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
from qdrant_client.models import SparseVector

from vue_docs_core.clients.qdrant import SearchHit
from vue_docs_core.models.entity import ApiEntity, EntityIndex, EntityType
from vue_docs_core.retrieval.reconstruction import (
    reconstruct_results,
    _file_path_to_url,
    _are_adjacent,
    _merge_adjacent_hits,
    _build_summary_line,
)
from vue_docs_core.retrieval.entity_matcher import (
    EntityMatcher,
    EntityMatchResult,
    _normalize_query,
    _tokenize,
    _is_word_boundary,
)
from vue_docs_server.startup import (
    ServerState,
    load_entity_dictionary,
    load_synonym_table,
    load_bm25_model,
)
from vue_docs_server.tools.search import _detect_entities, vue_docs_search
from vue_docs_server.tools.api_lookup import vue_api_lookup, _clean_section_title


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hit(
    chunk_id: str = "guide/essentials/computed#computed-caching",
    score: float = 0.85,
    file_path: str = "guide/essentials/computed.md",
    page_title: str = "Computed Properties",
    section_title: str = "Computed Caching",
    breadcrumb: str = "Guide > Essentials > Computed Properties > Computed Caching",
    global_sort_key: str = "02_guide/01_essentials/03_computed/01_caching",
    chunk_type: str = "section",
    content: str = "A computed property will only re-evaluate when some of its reactive dependencies have changed.",
    language_tag: str = "",
    preceding_prose: str = "",
    api_entities: list[str] | None = None,
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        payload={
            "chunk_id": chunk_id,
            "file_path": file_path,
            "folder_path": file_path.rsplit("/", 1)[0] if "/" in file_path else "",
            "page_title": page_title,
            "section_title": section_title,
            "subsection_title": "",
            "breadcrumb": breadcrumb,
            "global_sort_key": global_sort_key,
            "chunk_type": chunk_type,
            "content_type": "text",
            "language_tag": language_tag,
            "preceding_prose": preceding_prose,
            "api_entities": api_entities or [],
            "content": content,
        },
    )


def _make_entity_index() -> EntityIndex:
    """Build an entity index for testing."""
    return EntityIndex(
        entities={
            "ref": ApiEntity(name="ref", entity_type=EntityType.COMPOSABLE),
            "computed": ApiEntity(name="computed", entity_type=EntityType.COMPOSABLE),
            "defineProps": ApiEntity(name="defineProps", entity_type=EntityType.COMPILER_MACRO),
            "defineEmits": ApiEntity(name="defineEmits", entity_type=EntityType.COMPILER_MACRO),
            "v-model": ApiEntity(name="v-model", entity_type=EntityType.DIRECTIVE),
            "watchEffect": ApiEntity(name="watchEffect", entity_type=EntityType.COMPOSABLE),
            "onMounted": ApiEntity(name="onMounted", entity_type=EntityType.LIFECYCLE_HOOK),
            "onUnmounted": ApiEntity(name="onUnmounted", entity_type=EntityType.LIFECYCLE_HOOK),
            "reactive": ApiEntity(name="reactive", entity_type=EntityType.COMPOSABLE),
            "shallowRef": ApiEntity(name="shallowRef", entity_type=EntityType.COMPOSABLE),
            "Transition": ApiEntity(name="Transition", entity_type=EntityType.COMPONENT),
            "h": ApiEntity(name="h", entity_type=EntityType.GLOBAL_API),
            "is": ApiEntity(name="is", entity_type=EntityType.DIRECTIVE),
        }
    )


def _make_synonym_table() -> dict[str, list[str]]:
    return {
        "two-way binding": ["v-model"],
        "lifecycle": ["onMounted", "onUnmounted"],
        "reactivity": ["ref", "reactive"],
    }


def _make_matcher() -> EntityMatcher:
    return EntityMatcher(
        entity_index=_make_entity_index(),
        synonym_table=_make_synonym_table(),
    )


# ---------------------------------------------------------------------------
# Tests: Reconstruction
# ---------------------------------------------------------------------------


class TestReconstruction:
    def test_empty_hits(self):
        result = reconstruct_results([])
        assert result == "No results found."

    def test_single_hit_format(self):
        hits = [_make_hit()]
        result = reconstruct_results(hits)
        assert "Computed Properties" in result
        assert "vuejs.org" in result
        assert "re-evaluate" in result
        assert "Found 1 relevant" in result

    def test_code_block_rendering(self):
        hits = [
            _make_hit(
                chunk_type="code_block",
                content="const count = ref(0)",
                language_tag="js",
                preceding_prose="Here is a basic example:",
            )
        ]
        result = reconstruct_results(hits)
        assert "```js" in result
        assert "const count = ref(0)" in result
        assert "Here is a basic example:" in result

    def test_sort_by_global_sort_key(self):
        """Results should be ordered by sort key, not by score."""
        hits = [
            _make_hit(
                chunk_id="b",
                score=0.9,
                global_sort_key="02_second",
                section_title="Second",
                content="Second section",
            ),
            _make_hit(
                chunk_id="a",
                score=0.5,
                global_sort_key="01_first",
                section_title="First",
                content="First section",
            ),
        ]
        result = reconstruct_results(hits)
        first_pos = result.index("First section")
        second_pos = result.index("Second section")
        assert first_pos < second_pos

    def test_grouped_by_page(self):
        hits = [
            _make_hit(file_path="guide/a.md", page_title="Page A", content="Content A"),
            _make_hit(file_path="guide/b.md", page_title="Page B", content="Content B"),
        ]
        result = reconstruct_results(hits)
        assert "## Page A" in result
        assert "## Page B" in result

    def test_api_entities_displayed(self):
        hits = [_make_hit(api_entities=["computed", "ref"])]
        result = reconstruct_results(hits)
        assert "`computed`" in result
        assert "`ref`" in result

    def test_max_results_limit(self):
        hits = [_make_hit(chunk_id=f"chunk_{i}", content=f"Content {i}") for i in range(20)]
        result = reconstruct_results(hits, max_results=5)
        assert "Found 5 relevant" in result

    def test_file_path_to_url(self):
        assert _file_path_to_url("guide/essentials/computed.md") == "https://vuejs.org/guide/essentials/computed"
        assert _file_path_to_url("/api/reactivity-core.md") == "https://vuejs.org/api/reactivity-core"

    def test_image_chunk_rendering(self):
        hits = [
            _make_hit(
                chunk_type="image",
                content="Reactivity diagram showing dependency tracking",
                preceding_prose="The following diagram shows how reactivity works:",
            )
        ]
        result = reconstruct_results(hits)
        assert "[Image:" in result
        assert "Reactivity diagram" in result

    def test_cross_references_displayed(self):
        hit = _make_hit()
        hit.payload["cross_references"] = ["guide/essentials/watchers.md", "api/reactivity-core.md"]
        result = reconstruct_results([hit])
        assert "See also:" in result
        assert "vuejs.org/guide/essentials/watchers" in result

    def test_summary_line_with_entities(self):
        hits = [
            _make_hit(api_entities=["computed", "ref"]),
            _make_hit(
                chunk_id="other",
                file_path="guide/other.md",
                page_title="Other",
                api_entities=["reactive"],
            ),
        ]
        result = reconstruct_results(hits)
        assert "across 2 pages" in result
        assert "Related APIs:" in result
        assert "`computed`" in result

    def test_summary_line_single_page(self):
        hits = [_make_hit()]
        result = reconstruct_results(hits)
        assert "Found 1 relevant" in result
        # Should NOT say "across X pages" for single page
        assert "across" not in result.split("\n")[0]


class TestAdjacentMerging:
    def test_adjacent_same_section(self):
        a = _make_hit(
            chunk_id="a",
            global_sort_key="02_guide/01_ess/01_first",
            section_title="Section",
        )
        b = _make_hit(
            chunk_id="b",
            global_sort_key="02_guide/01_ess/02_second",
            section_title="Section",
        )
        assert _are_adjacent(a, b)

    def test_not_adjacent_different_sections(self):
        a = _make_hit(
            chunk_id="a",
            global_sort_key="02_guide/01_ess/01_first",
            section_title="Section A",
        )
        b = _make_hit(
            chunk_id="b",
            global_sort_key="02_guide/01_ess/02_second",
            section_title="Section B",
        )
        assert not _are_adjacent(a, b)

    def test_not_adjacent_different_files(self):
        a = _make_hit(chunk_id="a", file_path="guide/a.md", global_sort_key="01_a/01")
        b = _make_hit(chunk_id="b", file_path="guide/b.md", global_sort_key="01_b/01")
        assert not _are_adjacent(a, b)

    def test_not_adjacent_non_consecutive(self):
        a = _make_hit(
            chunk_id="a",
            global_sort_key="02_guide/01_ess/01_first",
            section_title="Section",
        )
        b = _make_hit(
            chunk_id="b",
            global_sort_key="02_guide/01_ess/05_fifth",
            section_title="Section",
        )
        assert not _are_adjacent(a, b)

    def test_merge_groups(self):
        hits = [
            _make_hit(
                chunk_id="a",
                global_sort_key="02_guide/01_ess/01_first",
                section_title="Section",
            ),
            _make_hit(
                chunk_id="b",
                global_sort_key="02_guide/01_ess/02_second",
                section_title="Section",
            ),
            _make_hit(
                chunk_id="c",
                global_sort_key="02_guide/02_other/01_first",
                section_title="Other",
            ),
        ]
        groups = _merge_adjacent_hits(hits)
        assert len(groups) == 2
        assert len(groups[0]) == 2  # a and b merged
        assert len(groups[1]) == 1  # c alone

    def test_merged_chunks_skip_heading(self):
        """Second chunk in merged group should not repeat the section heading."""
        hits = [
            _make_hit(
                chunk_id="a",
                global_sort_key="02_guide/01_ess/01_first",
                section_title="My Section",
                content="First content",
            ),
            _make_hit(
                chunk_id="b",
                global_sort_key="02_guide/01_ess/02_second",
                section_title="My Section",
                content="Second content",
            ),
        ]
        result = reconstruct_results(hits)
        # Section heading should appear only once
        assert result.count("### My Section") == 1
        assert "First content" in result
        assert "Second content" in result


class TestBuildSummaryLine:
    def test_basic_summary(self):
        hits = [_make_hit()]
        summary = _build_summary_line(hits)
        assert "Found 1 relevant" in summary

    def test_multi_page_summary(self):
        hits = [
            _make_hit(file_path="guide/a.md"),
            _make_hit(file_path="guide/b.md"),
            _make_hit(file_path="guide/c.md"),
        ]
        summary = _build_summary_line(hits)
        assert "across 3 pages" in summary

    def test_entities_in_summary(self):
        hits = [_make_hit(api_entities=["computed", "ref"])]
        summary = _build_summary_line(hits)
        assert "`computed`" in summary
        assert "`ref`" in summary

    def test_many_entities_truncated(self):
        entities = [f"api{i}" for i in range(12)]
        hits = [_make_hit(api_entities=entities)]
        summary = _build_summary_line(hits)
        assert "and 4 more" in summary


# ---------------------------------------------------------------------------
# Tests: Startup State Loading
# ---------------------------------------------------------------------------


class TestStartup:
    def test_server_state_not_ready_initially(self):
        s = ServerState()
        assert not s.is_ready

    def test_server_state_ready_when_initialized(self):
        s = ServerState()
        s.qdrant = MagicMock()
        s.bm25 = MagicMock()
        assert s.is_ready

    def test_load_entity_dictionary(self, tmp_path):
        data = {
            "ref": {"entity_type": "composable", "page_path": "api/reactivity-core", "section": "ref()"},
            "computed": {"entity_type": "composable", "page_path": "api/reactivity-core", "section": "computed()"},
        }
        dict_path = tmp_path / "entity_dictionary.json"
        dict_path.write_text(json.dumps(data))

        index = load_entity_dictionary(tmp_path)
        assert len(index.entities) == 2
        assert "ref" in index.entities
        assert index.entities["ref"].page_path == "api/reactivity-core"
        assert index.entities["ref"].entity_type == EntityType.COMPOSABLE

    def test_load_entity_dictionary_missing(self, tmp_path):
        index = load_entity_dictionary(tmp_path)
        assert len(index.entities) == 0

    def test_load_synonym_table(self, tmp_path):
        data = {"two-way binding": ["v-model"], "reactivity": ["ref", "reactive"]}
        syn_path = tmp_path / "synonym_table.json"
        syn_path.write_text(json.dumps(data))

        table = load_synonym_table(tmp_path)
        assert len(table) == 2
        assert table["two-way binding"] == ["v-model"]

    def test_load_synonym_table_missing(self, tmp_path):
        table = load_synonym_table(tmp_path)
        assert table == {}


# ---------------------------------------------------------------------------
# Tests: Entity Matcher (core module)
# ---------------------------------------------------------------------------


class TestEntityMatcherHelpers:
    def test_normalize_query(self):
        assert _normalize_query("  What is `ref`?  ") == "what is ref?"
        assert _normalize_query("`defineProps` usage") == "defineprops usage"

    def test_tokenize(self):
        tokens = _tokenize("how does ref work?")
        assert tokens == ["how", "does", "ref", "work"]

    def test_tokenize_hyphens(self):
        tokens = _tokenize("v-model two-way binding")
        assert tokens == ["v", "model", "two", "way", "binding"]

    def test_is_word_boundary(self):
        assert _is_word_boundary("how does ref work", "ref")
        assert not _is_word_boundary("preference settings", "ref")
        assert _is_word_boundary("use `ref` here", "ref")


class TestEntityMatcherExact:
    def test_exact_match_simple(self):
        matcher = _make_matcher()
        result = matcher.match("how does computed work?")
        assert "computed" in result.entities
        assert result.match_sources["computed"] == "exact"

    def test_exact_match_case_insensitive(self):
        matcher = _make_matcher()
        result = matcher.match("What is Transition?")
        assert "Transition" in result.entities

    def test_exact_match_hyphenated(self):
        matcher = _make_matcher()
        result = matcher.match("how to use v-model")
        assert "v-model" in result.entities

    def test_exact_match_backtick_stripped(self):
        matcher = _make_matcher()
        result = matcher.match("what does `defineProps` do?")
        assert "defineProps" in result.entities

    def test_exact_match_multiple(self):
        matcher = _make_matcher()
        result = matcher.match("difference between ref and computed")
        assert "ref" in result.entities
        assert "computed" in result.entities

    def test_short_name_word_boundary(self):
        """Short names like 'h' and 'is' should not match as substrings."""
        matcher = _make_matcher()
        result = matcher.match("this is how to handle things")
        # "is" should not match inside "this is how"
        # "h" should not match inside "how" or "handle" or "things"
        assert "h" not in result.entities

    def test_no_matches(self):
        matcher = _make_matcher()
        result = matcher.match("how to deploy a web app")
        # Should have no exact matches for our entity set
        assert len([e for e in result.entities if result.match_sources.get(e) == "exact"]) == 0


class TestEntityMatcherBigram:
    def test_bigram_watcheffect(self):
        matcher = _make_matcher()
        result = matcher.match("how does watch effect work")
        assert "watchEffect" in result.entities
        assert result.match_sources["watchEffect"] == "bigram"

    def test_bigram_defineprops(self):
        matcher = _make_matcher()
        result = matcher.match("how to define props in vue")
        assert "defineProps" in result.entities

    def test_bigram_shallowref(self):
        matcher = _make_matcher()
        result = matcher.match("when to use shallow ref")
        assert "shallowRef" in result.entities


class TestEntityMatcherSynonym:
    def test_synonym_two_way_binding(self):
        matcher = _make_matcher()
        result = matcher.match("how to do two-way binding?")
        assert "v-model" in result.entities
        assert result.match_sources["v-model"] == "synonym"

    def test_synonym_lifecycle(self):
        matcher = _make_matcher()
        result = matcher.match("what are lifecycle hooks?")
        assert "onMounted" in result.entities
        assert "onUnmounted" in result.entities

    def test_synonym_reactivity(self):
        matcher = _make_matcher()
        result = matcher.match("explain vue reactivity system")
        assert "ref" in result.entities
        assert "reactive" in result.entities


class TestEntityMatcherFuzzy:
    def test_fuzzy_typo_defineprops(self):
        """'definProps' (missing 'e') should fuzzy-match to 'defineProps'."""
        matcher = _make_matcher()
        result = matcher.match("what is definProps")
        assert "defineProps" in result.entities
        assert result.match_sources["defineProps"] == "fuzzy"

    def test_fuzzy_typo_onmounted(self):
        """'onmounte' should fuzzy-match to 'onMounted'."""
        matcher = _make_matcher()
        result = matcher.match("when does onmounte fire")
        assert "onMounted" in result.entities

    def test_fuzzy_no_false_positive_short(self):
        """Short entity names should not fuzzy match."""
        matcher = _make_matcher()
        result = matcher.match("re things")
        # "re" should NOT fuzzy-match to "ref" since "ref" is only 3 chars
        assert "ref" not in [
            e for e in result.entities if result.match_sources.get(e) == "fuzzy"
        ]


class TestEntityMatcherPriority:
    def test_exact_takes_priority_over_fuzzy(self):
        """If exact match found, the same entity shouldn't appear as fuzzy."""
        matcher = _make_matcher()
        result = matcher.match("computed properties")
        assert result.match_sources.get("computed") == "exact"

    def test_no_duplicates(self):
        """Each entity appears only once even if multiple methods match."""
        matcher = _make_matcher()
        result = matcher.match("ref and reactivity")
        # "ref" matched by exact AND synonym for "reactivity", but should appear once
        assert result.entities.count("ref") == 1


# ---------------------------------------------------------------------------
# Tests: Entity Detection in Search (integration with server state)
# ---------------------------------------------------------------------------


class TestEntityDetection:
    def setup_method(self):
        """Set up server state for entity detection tests."""
        from vue_docs_server.startup import state as server_state

        entity_index = _make_entity_index()
        synonym_table = _make_synonym_table()

        server_state.entity_index = entity_index
        server_state.synonym_table = synonym_table
        server_state.entity_matcher = EntityMatcher(
            entity_index=entity_index,
            synonym_table=synonym_table,
        )

    def test_detect_inline_entity(self):
        detected = _detect_entities("how does computed work?")
        assert "computed" in detected

    def test_detect_backtick_entity(self):
        detected = _detect_entities("what does `defineProps` do?")
        assert "defineProps" in detected

    def test_detect_synonym(self):
        detected = _detect_entities("how to do two-way binding?")
        assert "v-model" in detected

    def test_detect_multiple(self):
        detected = _detect_entities("difference between ref and computed")
        assert "ref" in detected
        assert "computed" in detected

    def test_no_matches(self):
        detected = _detect_entities("how to deploy a web app")
        # May have some matches depending on substrings, but no Vue-specific entities
        for entity in detected:
            # Only check that any detected entity is actually in the dictionary
            assert entity in _make_entity_index().entities

    def test_detect_fuzzy_typo(self):
        detected = _detect_entities("what is definProps")
        assert "defineProps" in detected

    def test_detect_with_no_matcher(self):
        """When entity_matcher is None, returns empty list."""
        from vue_docs_server.startup import state as server_state
        server_state.entity_matcher = None
        detected = _detect_entities("computed properties")
        assert detected == []


# ---------------------------------------------------------------------------
# Tests: API Lookup Tool
# ---------------------------------------------------------------------------


class TestApiLookup:
    def setup_method(self):
        from vue_docs_server.startup import state as server_state

        server_state.entity_index = EntityIndex(
            entities={
                "ref": ApiEntity(
                    name="ref",
                    entity_type=EntityType.COMPOSABLE,
                    page_path="api/reactivity-core.md",
                    section="ref() {#ref}",
                    related=["reactive", "unref", "isRef"],
                ),
                "defineProps": ApiEntity(
                    name="defineProps",
                    entity_type=EntityType.COMPILER_MACRO,
                    page_path="api/sfc-script-setup.md",
                    section="defineProps() & defineEmits() {#defineprops-defineemits}",
                    related=["defineEmits"],
                ),
                "v-model": ApiEntity(
                    name="v-model",
                    entity_type=EntityType.DIRECTIVE,
                    page_path="api/built-in-directives.md",
                    section="v-model {#v-model}",
                ),
                "onMounted": ApiEntity(
                    name="onMounted",
                    entity_type=EntityType.LIFECYCLE_HOOK,
                    page_path="api/composition-api-lifecycle.md",
                    section="onMounted() {#onmounted}",
                ),
            },
            entity_to_chunks={
                "ref": ["api/reactivity-core#ref", "guide/essentials/reactivity#ref"],
                "defineProps": ["api/sfc-script-setup#defineprops"],
            },
        )
        server_state.synonym_table = {"two-way binding": ["v-model"]}
        server_state.entity_matcher = EntityMatcher(
            entity_index=server_state.entity_index,
            synonym_table=server_state.synonym_table,
        )
        server_state.qdrant = MagicMock()
        server_state.bm25 = MagicMock()

    @pytest.mark.asyncio
    async def test_lookup_exact(self):
        result = await vue_api_lookup("ref")
        assert "# `ref`" in result
        assert "Composable" in result
        assert "vuejs.org/api/reactivity-core" in result
        assert "`reactive`" in result  # related APIs
        assert "2 documentation chunks" in result

    @pytest.mark.asyncio
    async def test_lookup_case_insensitive(self):
        result = await vue_api_lookup("REF")
        assert "# `ref`" in result

    @pytest.mark.asyncio
    async def test_lookup_with_backticks(self):
        result = await vue_api_lookup("`defineProps`")
        assert "# `defineProps`" in result
        assert "Compiler Macro" in result

    @pytest.mark.asyncio
    async def test_lookup_hyphenated(self):
        result = await vue_api_lookup("v-model")
        assert "# `v-model`" in result
        assert "Directive" in result

    @pytest.mark.asyncio
    async def test_lookup_fuzzy_fallback(self):
        """Fuzzy matching catches typos."""
        result = await vue_api_lookup("onMounte")
        assert "# `onMounted`" in result

    @pytest.mark.asyncio
    async def test_lookup_not_found(self):
        result = await vue_api_lookup("nonExistentApi")
        assert "No API entity found" in result
        assert "vue_docs_search" in result

    @pytest.mark.asyncio
    async def test_lookup_not_ready(self):
        from vue_docs_server.startup import state as server_state
        server_state.qdrant = None
        server_state.bm25 = None
        result = await vue_api_lookup("ref")
        assert "not initialized" in result

    @pytest.mark.asyncio
    async def test_lookup_section_cleaned(self):
        result = await vue_api_lookup("defineProps")
        assert "{#" not in result  # anchor markers removed
        assert "defineProps() & defineEmits()" in result


class TestCleanSectionTitle:
    def test_simple_anchor(self):
        assert _clean_section_title("ref() {#ref}") == "ref()"

    def test_html_badge(self):
        result = _clean_section_title(
            'useTemplateRef() <sup class="vt-badge" data-text="3.5+" /> {#usetemplateref}'
        )
        assert result == "useTemplateRef()"

    def test_backticks(self):
        assert _clean_section_title("`<Transition>` {#transition}") == "<Transition>"


# ---------------------------------------------------------------------------
# Tests: Search Tool (mocked Jina + Qdrant)
# ---------------------------------------------------------------------------


class TestSearchTool:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """End-to-end search with mocked Jina and Qdrant."""
        from vue_docs_server.startup import state as server_state

        # Set up state
        mock_qdrant = MagicMock()
        mock_qdrant.hybrid_search.return_value = [
            _make_hit(content="Computed properties are cached based on reactive deps.")
        ]
        server_state.qdrant = mock_qdrant

        mock_bm25 = MagicMock()
        mock_bm25.get_query_sparse_vector.return_value = SparseVector(
            indices=[1, 5], values=[1.0, 1.0]
        )
        server_state.bm25 = mock_bm25

        entity_index = EntityIndex(
            entities={"computed": ApiEntity(name="computed")}
        )
        server_state.entity_index = entity_index
        server_state.synonym_table = {}
        server_state.entity_matcher = EntityMatcher(
            entity_index=entity_index,
            synonym_table={},
        )

        # Mock Jina embedding
        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with patch("vue_docs_server.tools.search.JinaClient") as MockJina:
            mock_jina_instance = AsyncMock()
            mock_jina_instance.embed.return_value = mock_embed_result
            mock_jina_instance.close = AsyncMock()
            MockJina.return_value = mock_jina_instance

            result = await vue_docs_search("how does computed caching work")

        assert "Computed Properties" in result
        assert "cached" in result
        mock_qdrant.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_not_ready(self):
        """Search returns error when server not initialized."""
        from vue_docs_server.startup import state as server_state

        server_state.qdrant = None
        server_state.bm25 = None

        result = await vue_docs_search("test query")
        assert "not initialized" in result

    @pytest.mark.asyncio
    async def test_search_scope_fallback(self):
        """When scoped search returns empty, retries with broader scope."""
        from vue_docs_server.startup import state as server_state

        mock_qdrant = MagicMock()
        # First call (scoped) returns empty, second call (all) returns results
        mock_qdrant.hybrid_search.side_effect = [
            [],
            [_make_hit(content="Found with broader scope")],
        ]
        server_state.qdrant = mock_qdrant

        mock_bm25 = MagicMock()
        mock_bm25.get_query_sparse_vector.return_value = SparseVector(
            indices=[1], values=[1.0]
        )
        server_state.bm25 = mock_bm25
        server_state.entity_index = EntityIndex()
        server_state.synonym_table = {}
        server_state.entity_matcher = EntityMatcher(
            entity_index=EntityIndex(),
            synonym_table={},
        )

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with patch("vue_docs_server.tools.search.JinaClient") as MockJina:
            mock_jina_instance = AsyncMock()
            mock_jina_instance.embed.return_value = mock_embed_result
            mock_jina_instance.close = AsyncMock()
            MockJina.return_value = mock_jina_instance

            result = await vue_docs_search("test", scope="tutorial")

        assert "broader scope" in result
        assert mock_qdrant.hybrid_search.call_count == 2


# ---------------------------------------------------------------------------
# Tests: MCP Tool Registration
# ---------------------------------------------------------------------------


class TestMCPRegistration:
    def test_mcp_app_has_tools(self):
        """Verify the MCP app has the search tool registered."""
        from vue_docs_server.main import mcp

        # FastMCP stores tools internally
        assert mcp is not None
        assert mcp.name == "Vue Docs MCP Server"


# ---------------------------------------------------------------------------
# Tests: MCP Protocol Integration (fastmcp.Client in-process)
# ---------------------------------------------------------------------------


def _setup_server_state():
    """Configure mocked server state for integration tests."""
    from vue_docs_server.startup import state as server_state

    mock_qdrant = MagicMock()
    mock_qdrant.hybrid_search.return_value = [
        _make_hit(
            content="A computed property will only re-evaluate when some of its reactive dependencies have changed.",
            api_entities=["computed"],
        )
    ]
    mock_qdrant.collection_info.return_value = {"points_count": 500, "status": "green"}
    server_state.qdrant = mock_qdrant

    mock_bm25 = MagicMock()
    mock_bm25.get_query_sparse_vector.return_value = SparseVector(
        indices=[1, 5], values=[1.0, 1.0]
    )
    server_state.bm25 = mock_bm25

    entity_index = EntityIndex(
        entities={
            "ref": ApiEntity(
                name="ref",
                entity_type=EntityType.COMPOSABLE,
                page_path="api/reactivity-core.md",
                section="ref() {#ref}",
                related=["reactive", "unref"],
            ),
            "computed": ApiEntity(
                name="computed",
                entity_type=EntityType.COMPOSABLE,
                page_path="api/reactivity-core.md",
                section="computed() {#computed}",
            ),
            "v-model": ApiEntity(
                name="v-model",
                entity_type=EntityType.DIRECTIVE,
                page_path="api/built-in-directives.md",
                section="v-model {#v-model}",
            ),
        },
        entity_to_chunks={
            "ref": ["api/reactivity-core#ref"],
        },
    )
    server_state.entity_index = entity_index
    server_state.synonym_table = {
        "two-way binding": ["v-model"],
        "reactivity": ["ref", "reactive"],
    }
    server_state.entity_matcher = EntityMatcher(
        entity_index=entity_index,
        synonym_table=server_state.synonym_table,
    )
    return server_state


class TestMCPIntegration:
    """End-to-end tests via the MCP protocol using fastmcp.Client.

    These tests exercise the full MCP request/response cycle in-process:
    Client -> MCP protocol -> FastMCP tool dispatch -> our tool function -> response.
    Jina and Qdrant are mocked, but the MCP layer is real.

    The lifespan's startup/shutdown are patched to avoid connecting to real
    services — instead, _setup_server_state() injects mocks into the singleton.
    """

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Server exposes both tools via MCP."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        tool_names = [t.name for t in tools]
        assert "vue_docs_search_tool" in tool_names
        assert "vue_api_lookup_tool" in tool_names

    @pytest.mark.asyncio
    async def test_tool_schema(self):
        """Search tool has correct parameter schema."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        search_tool = next(t for t in tools if t.name == "vue_docs_search_tool")
        params = search_tool.inputSchema
        assert "query" in params["properties"]
        assert "scope" in params["properties"]
        assert "max_results" in params["properties"]
        assert "query" in params.get("required", [])

    @pytest.mark.asyncio
    async def test_api_lookup_tool_schema(self):
        """API lookup tool has correct parameter schema."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        lookup_tool = next(t for t in tools if t.name == "vue_api_lookup_tool")
        params = lookup_tool.inputSchema
        assert "api_name" in params["properties"]
        assert "api_name" in params.get("required", [])

    @pytest.mark.asyncio
    async def test_call_search_tool(self):
        """Call vue_docs_search_tool through MCP protocol and get results."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search_tool",
                    {"query": "how does computed caching work"},
                )

        assert not result.is_error
        assert len(result.content) > 0
        text = result.content[0].text
        assert "Computed Properties" in text
        assert "re-evaluate" in text

    @pytest.mark.asyncio
    async def test_call_api_lookup_tool(self):
        """Call vue_api_lookup_tool through MCP protocol."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_api_lookup_tool",
                    {"api_name": "ref"},
                )

        assert not result.is_error
        text = result.content[0].text
        assert "# `ref`" in text
        assert "Composable" in text
        assert "vuejs.org/api/reactivity-core" in text

    @pytest.mark.asyncio
    async def test_call_search_tool_with_scope(self):
        """Search tool respects the scope parameter."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search_tool",
                    {"query": "ref basics", "scope": "guide/essentials", "max_results": 5},
                )

        # Verify Qdrant was called with the scope filter
        call_kwargs = server_state.qdrant.hybrid_search.call_args
        assert call_kwargs.kwargs.get("scope_filter") == "guide/essentials"
        assert call_kwargs.kwargs.get("limit") == 15  # max_results * 3

    @pytest.mark.asyncio
    async def test_call_search_tool_entity_boost(self):
        """Detected entities are passed as boost filter to Qdrant."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search_tool",
                    {"query": "how does computed work"},
                )

        call_kwargs = server_state.qdrant.hybrid_search.call_args
        entity_boost = call_kwargs.kwargs.get("entity_boost")
        assert entity_boost is not None
        assert "computed" in entity_boost

    @pytest.mark.asyncio
    async def test_server_instructions(self):
        """Server provides instructions to the client."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                info = client.initialize_result
                assert info is not None
                assert info.serverInfo.name == "Vue Docs MCP Server"
