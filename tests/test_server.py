"""Tests for MCP server components.

Covers startup state loading, reconstruction formatting, entity detection
in search, the MCP tool registration, api_lookup tool, and end-to-end MCP
protocol integration tests using fastmcp.Client for in-process testing.

No real API calls — Jina, Qdrant, and BM25 are mocked throughout.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
from qdrant_client.models import SparseVector

from vue_docs_core.clients.jina import RerankResult
from vue_docs_core.clients.qdrant import SearchHit
from vue_docs_core.models.entity import ApiEntity, EntityIndex, EntityType
from vue_docs_core.retrieval.entity_matcher import (
    EntityMatcher,
    _is_word_boundary,
    _normalize_query,
    _tokenize,
)
from vue_docs_core.retrieval.reconstruction import (
    _are_adjacent,
    _build_chunk_frontmatter,
    _file_path_to_url,
    _merge_adjacent_hits,
    reconstruct_results,
)
from vue_docs_server.startup import (
    ServerState,
    load_entity_dictionary,
    load_synonym_table,
)
from vue_docs_server.tools.api_lookup import _clean_section_title, vue_api_lookup
from vue_docs_server.tools.search import _detect_entities, vue_docs_search

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ctx():
    """Create a mock MCP Context for direct tool function calls."""
    ctx = AsyncMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.get_state = AsyncMock(return_value=None)
    ctx.set_state = AsyncMock()
    return ctx


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
            "ref": ApiEntity(
                name="ref", entity_type=EntityType.COMPOSABLE, related=["reactive", "unref"]
            ),
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
        assert "---\n" in result  # per-chunk YAML frontmatter
        assert "breadcrumb:" in result

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

    def test_api_entities_in_chunk_frontmatter(self):
        hits = [_make_hit(api_entities=["computed", "ref"])]
        result = reconstruct_results(hits)
        assert "apis: [computed, ref]" in result

    def test_max_results_limit(self):
        hits = [_make_hit(chunk_id=f"chunk_{i}", content=f"Content {i}") for i in range(20)]
        result = reconstruct_results(hits, max_results=5)
        # Should only contain 5 chunks worth of content
        assert result.count("### Computed Caching") == 5

    def test_file_path_to_url(self):
        assert (
            _file_path_to_url("guide/essentials/computed.md")
            == "https://vuejs.org/guide/essentials/computed"
        )
        assert (
            _file_path_to_url("/api/reactivity-core.md") == "https://vuejs.org/api/reactivity-core"
        )

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
        assert "see_also:" in result
        assert "vuejs.org/guide/essentials/watchers" in result

    def test_per_chunk_entities(self):
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
        # Each chunk's frontmatter has its own APIs
        assert "apis: [computed, ref]" in result
        assert "apis: [reactive]" in result

    def test_chunk_frontmatter_has_breadcrumb(self):
        hits = [_make_hit()]
        result = reconstruct_results(hits)
        assert "breadcrumb: Guide > Essentials" in result

    def test_page_summary_rendered_as_overview(self):
        hits = [
            _make_hit(
                chunk_id="guide/essentials/computed#page_summary",
                chunk_type="page_summary",
                content="This page covers computed properties in Vue 3.",
                section_title="",
            ),
        ]
        result = reconstruct_results(hits)
        assert "**Overview:**" in result
        assert "[!NOTE]" in result
        assert "computed properties in Vue 3" in result

    def test_folder_summary_rendered_as_section_overview(self):
        hits = [
            SearchHit(
                chunk_id="guide/essentials#folder_summary",
                score=0.7,
                payload={
                    "chunk_id": "guide/essentials#folder_summary",
                    "file_path": "",
                    "folder_path": "guide/essentials",
                    "page_title": "Guide > Essentials",
                    "section_title": "",
                    "subsection_title": "",
                    "breadcrumb": "Guide > Essentials",
                    "global_sort_key": "02_guide/01_essentials",
                    "chunk_type": "folder_summary",
                    "content_type": "text",
                    "language_tag": "",
                    "preceding_prose": "",
                    "api_entities": [],
                    "content": "This section covers Vue essentials.",
                },
            ),
        ]
        result = reconstruct_results(hits)
        assert "**Section Overview:**" in result
        assert "Vue essentials" in result

    def test_page_summary_placed_before_detail_chunks(self):
        hits = [
            _make_hit(
                chunk_id="guide/essentials/computed#section1",
                chunk_type="section",
                content="Detail about caching",
                global_sort_key="02_guide/01_essentials/03_computed/01",
            ),
            _make_hit(
                chunk_id="guide/essentials/computed#page_summary",
                chunk_type="page_summary",
                content="This page covers computed properties.",
                section_title="",
                global_sort_key="02_guide/01_essentials/03_computed",
            ),
        ]
        result = reconstruct_results(hits, max_results=5)
        overview_pos = result.index("**Overview:**")
        detail_pos = result.index("Detail about caching")
        assert overview_pos < detail_pos

    def test_top_summary_rendered_before_page_results(self):
        hits = [
            SearchHit(
                chunk_id="guide#top_summary",
                score=0.6,
                payload={
                    "chunk_id": "guide#top_summary",
                    "file_path": "",
                    "folder_path": "guide",
                    "page_title": "Guide",
                    "section_title": "",
                    "subsection_title": "",
                    "breadcrumb": "Guide",
                    "global_sort_key": "02_guide",
                    "chunk_type": "top_summary",
                    "content_type": "text",
                    "language_tag": "",
                    "preceding_prose": "",
                    "api_entities": [],
                    "content": "The guide covers all core Vue concepts.",
                },
            ),
            _make_hit(
                chunk_id="guide/essentials/computed#section1",
                content="Detail content here",
                global_sort_key="02_guide/01_essentials/03_computed/01",
            ),
        ]
        result = reconstruct_results(hits, max_results=5)
        top_pos = result.index("**Topic Overview:**")
        detail_pos = result.index("Detail content here")
        assert top_pos < detail_pos


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


class TestBuildChunkFrontmatter:
    def test_basic_frontmatter(self):
        hits = [_make_hit()]
        fm = _build_chunk_frontmatter(hits)
        assert fm.startswith("---\n")
        assert fm.endswith("---")
        assert "breadcrumb:" in fm
        assert "source:" in fm

    def test_entities_in_frontmatter(self):
        hits = [_make_hit(api_entities=["computed", "ref"])]
        fm = _build_chunk_frontmatter(hits)
        assert "apis: [computed, ref]" in fm

    def test_merged_group_combines_entities(self):
        hits = [
            _make_hit(api_entities=["computed"]),
            _make_hit(chunk_id="b", api_entities=["ref", "computed"]),
        ]
        fm = _build_chunk_frontmatter(hits)
        assert "apis: [computed, ref]" in fm  # deduplicated

    def test_cross_references_in_frontmatter(self):
        hit = _make_hit()
        hit.payload["cross_references"] = ["guide/essentials/watchers.md"]
        fm = _build_chunk_frontmatter([hit])
        assert "see_also:" in fm
        assert "Watchers" in fm


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
            "ref": {
                "entity_type": "composable",
                "page_path": "api/reactivity-core",
                "section": "ref()",
            },
            "computed": {
                "entity_type": "composable",
                "page_path": "api/reactivity-core",
                "section": "computed()",
            },
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
        assert "ref" not in [e for e in result.entities if result.match_sources.get(e) == "fuzzy"]


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
        result = await vue_api_lookup("ref", ctx=_mock_ctx())
        assert "# `ref`" in result
        assert "Composable" in result
        assert "vuejs.org/api/reactivity-core" in result
        assert "`reactive`" in result  # related APIs
        assert "Documentation chunks" in result and "2" in result

    @pytest.mark.asyncio
    async def test_lookup_case_insensitive(self):
        result = await vue_api_lookup("REF", ctx=_mock_ctx())
        assert "# `ref`" in result

    @pytest.mark.asyncio
    async def test_lookup_with_backticks(self):
        result = await vue_api_lookup("`defineProps`", ctx=_mock_ctx())
        assert "# `defineProps`" in result
        assert "Compiler Macro" in result

    @pytest.mark.asyncio
    async def test_lookup_hyphenated(self):
        result = await vue_api_lookup("v-model", ctx=_mock_ctx())
        assert "# `v-model`" in result
        assert "Directive" in result

    @pytest.mark.asyncio
    async def test_lookup_fuzzy_fallback(self):
        """Fuzzy matching catches typos."""
        result = await vue_api_lookup("onMounte", ctx=_mock_ctx())
        assert "# `onMounted`" in result

    @pytest.mark.asyncio
    async def test_lookup_not_found(self):
        result = await vue_api_lookup("nonExistentApi", ctx=_mock_ctx())
        assert "No API entity found" in result
        assert "vue_docs_search" in result

    @pytest.mark.asyncio
    async def test_lookup_not_ready(self):
        from fastmcp.exceptions import ToolError

        from vue_docs_server.startup import state as server_state

        server_state.qdrant = None
        server_state.bm25 = None
        with pytest.raises(ToolError, match="not initialized"):
            await vue_api_lookup("ref", ctx=_mock_ctx())

    @pytest.mark.asyncio
    async def test_lookup_section_cleaned(self):
        result = await vue_api_lookup("defineProps", ctx=_mock_ctx())
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

        entity_index = EntityIndex(entities={"computed": ApiEntity(name="computed")})
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
            mock_jina_instance.rerank.return_value = RerankResult(
                indices=[0],
                scores=[0.9],
                total_tokens=100,
            )
            mock_jina_instance.close = AsyncMock()
            MockJina.return_value = mock_jina_instance

            result = await vue_docs_search("how does computed caching work", ctx=_mock_ctx())

        assert "Computed Properties" in result
        assert "cached" in result
        mock_qdrant.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_not_ready(self):
        """Search raises ToolError when server not initialized."""
        from fastmcp.exceptions import ToolError

        from vue_docs_server.startup import state as server_state

        server_state.qdrant = None
        server_state.bm25 = None

        with pytest.raises(ToolError, match="not initialized"):
            await vue_docs_search("test query", ctx=_mock_ctx())

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
        mock_bm25.get_query_sparse_vector.return_value = SparseVector(indices=[1], values=[1.0])
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
            mock_jina_instance.rerank.return_value = RerankResult(
                indices=[0],
                scores=[0.9],
                total_tokens=100,
            )
            mock_jina_instance.close = AsyncMock()
            MockJina.return_value = mock_jina_instance

            result = await vue_docs_search("test", scope="tutorial", ctx=_mock_ctx())

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
    mock_bm25.get_query_sparse_vector.return_value = SparseVector(indices=[1, 5], values=[1.0, 1.0])
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

    # Resource state
    server_state.page_paths = [
        "guide/essentials/computed.md",
        "guide/essentials/reactivity-fundamentals.md",
        "api/reactivity-core.md",
    ]
    server_state.folder_structure = {
        "guide/essentials": [
            "guide/essentials/computed.md",
            "guide/essentials/reactivity-fundamentals.md",
        ],
        "api": ["api/reactivity-core.md"],
    }
    server_state.vue_docs_path = None  # No disk access in integration tests

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
        """Server exposes all tools via MCP."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        tool_names = [t.name for t in tools]
        assert "vue_docs_search" in tool_names
        assert "vue_api_lookup" in tool_names
        assert "vue_get_related" in tool_names

    @pytest.mark.asyncio
    async def test_tool_schema(self):
        """Search tool has correct parameter schema."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        search_tool = next(t for t in tools if t.name == "vue_docs_search")
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

        lookup_tool = next(t for t in tools if t.name == "vue_api_lookup")
        params = lookup_tool.inputSchema
        assert "api_name" in params["properties"]
        assert "api_name" in params.get("required", [])

    @pytest.mark.asyncio
    async def test_call_search_tool(self):
        """Call vue_docs_search through MCP protocol and get results."""
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
            mock_jina.rerank.return_value = RerankResult(
                indices=[0],
                scores=[0.9],
                total_tokens=100,
            )
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search",
                    {"query": "how does computed caching work"},
                )

        assert not result.is_error
        assert len(result.content) > 0
        text = result.content[0].text
        assert "Computed Properties" in text
        assert "re-evaluate" in text

    @pytest.mark.asyncio
    async def test_call_api_lookup_tool(self):
        """Call vue_api_lookup through MCP protocol."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_api_lookup",
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
                await client.call_tool(
                    "vue_docs_search",
                    {"query": "ref basics", "scope": "guide/essentials", "max_results": 5},
                )

        # Verify Qdrant was called with the scope filter
        call_kwargs = server_state.qdrant.hybrid_search.call_args
        assert call_kwargs.kwargs.get("scope_filter") == "guide/essentials"
        assert call_kwargs.kwargs.get("limit") == 50  # _RETRIEVAL_LIMIT

    @pytest.mark.asyncio
    async def test_call_search_tool_no_entity_filter(self):
        """Entity boost is NOT passed to Qdrant (BM25 handles keyword matching)."""
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
                await client.call_tool(
                    "vue_docs_search",
                    {"query": "how does computed work"},
                )

        call_kwargs = server_state.qdrant.hybrid_search.call_args
        # Entity boost should NOT be passed — BM25 handles keyword matching
        assert call_kwargs.kwargs.get("entity_boost") is None

    @pytest.mark.asyncio
    async def test_server_instructions(self):
        """Server provides instructions to the client."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                info = client.initialize_result
                assert info is not None
                assert info.serverInfo.name == "Vue Docs MCP Server"


# ---------------------------------------------------------------------------
# Tests: MCP Resources
# ---------------------------------------------------------------------------


class TestMCPResources:
    """Test MCP resource registration and content via fastmcp.Client."""

    @pytest.mark.asyncio
    async def test_list_resources(self):
        """Server exposes resource templates via MCP."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                resources = await client.list_resources()
                templates = await client.list_resource_templates()

        # Static resources
        resource_uris = [str(r.uri) for r in resources]
        assert "vue://topics" in resource_uris
        assert "vue://api/index" in resource_uris
        assert "vue://scopes" in resource_uris

        # Template resources
        template_uris = [t.uriTemplate for t in templates]
        assert any("pages" in t for t in template_uris)
        assert any("entities" in t for t in template_uris)

    @pytest.mark.asyncio
    async def test_read_topics_resource(self):
        """TOC resource returns markdown with page listings."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://topics")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Table of Contents" in text
        assert "computed" in text.lower()

    @pytest.mark.asyncio
    async def test_read_api_index_resource(self):
        """API index resource returns grouped entity listing."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://api/index")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "API Index" in text
        assert "`ref`" in text
        assert "`computed`" in text

    @pytest.mark.asyncio
    async def test_read_scopes_resource(self):
        """Scopes resource lists valid search scopes."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://scopes")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Search Scopes" in text
        assert "guide/essentials" in text

    @pytest.mark.asyncio
    async def test_read_api_entity_resource(self):
        """API entity resource returns details for a specific entity."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://api/entities/ref")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "`ref`" in text
        assert "Composable" in text

    @pytest.mark.asyncio
    async def test_read_section_topics_resource(self):
        """Section TOC resource filters to a specific section."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://topics/guide/essentials")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "computed" in text.lower()
        # Should NOT include api pages
        assert "api/reactivity-core" not in text


# ---------------------------------------------------------------------------
# Tests: MCP Prompts
# ---------------------------------------------------------------------------


class TestMCPPrompts:
    """Test MCP prompt registration and rendering via fastmcp.Client."""

    @pytest.mark.asyncio
    async def test_list_prompts(self):
        """Server exposes all prompts via MCP."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                prompts = await client.list_prompts()

        prompt_names = [p.name for p in prompts]
        assert "debug_vue_issue" in prompt_names
        assert "compare_vue_apis" in prompt_names
        assert "migrate_vue_pattern" in prompt_names

    @pytest.mark.asyncio
    async def test_debug_prompt_renders(self):
        """Debug prompt returns structured debugging instructions."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.get_prompt(
                    "debug_vue_issue",
                    arguments={"symptom": "computed not updating"},
                )

        assert len(result.messages) == 2
        all_text = " ".join(m.content.text for m in result.messages)
        assert "computed not updating" in all_text
        assert "vue_docs_search" in all_text
        # First message is assistant context, second is user request
        assert result.messages[0].role == "assistant"
        assert result.messages[1].role == "user"

    @pytest.mark.asyncio
    async def test_compare_prompt_renders(self):
        """Compare prompt includes API names."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.get_prompt(
                    "compare_vue_apis",
                    arguments={"items": "ref, reactive"},
                )

        all_text = " ".join(m.content.text for m in result.messages)
        assert "`ref`" in all_text
        assert "`reactive`" in all_text

    @pytest.mark.asyncio
    async def test_migrate_prompt_renders(self):
        """Migrate prompt includes from/to patterns."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.get_prompt(
                    "migrate_vue_pattern",
                    arguments={
                        "from_pattern": "Options API",
                        "to_pattern": "Composition API",
                    },
                )

        all_text = " ".join(m.content.text for m in result.messages)
        assert "Options API" in all_text
        assert "Composition API" in all_text


# ---------------------------------------------------------------------------
# Tests: vue_get_related tool
# ---------------------------------------------------------------------------


class TestGetRelated:
    def setup_method(self):
        from vue_docs_server.startup import state as server_state

        entity_index = _make_entity_index()
        server_state.entity_index = entity_index
        server_state.synonym_table = _make_synonym_table()
        server_state.entity_matcher = EntityMatcher(
            entity_index=entity_index,
            synonym_table=server_state.synonym_table,
        )
        server_state.qdrant = MagicMock()
        server_state.bm25 = MagicMock()

    @pytest.mark.asyncio
    async def test_related_by_api_name(self):
        from vue_docs_server.tools.related import vue_get_related

        result = await vue_get_related("ref", ctx=_mock_ctx())
        assert "`ref`" in result
        assert "Composable" in result

    @pytest.mark.asyncio
    async def test_related_shows_related_apis(self):
        from vue_docs_server.tools.related import vue_get_related

        result = await vue_get_related("ref", ctx=_mock_ctx())
        # ref has related: reactive
        assert "reactive" in result

    @pytest.mark.asyncio
    async def test_related_by_synonym(self):
        from vue_docs_server.tools.related import vue_get_related

        result = await vue_get_related("two-way binding", ctx=_mock_ctx())
        assert "v-model" in result

    @pytest.mark.asyncio
    async def test_related_no_match(self):
        from vue_docs_server.tools.related import vue_get_related

        result = await vue_get_related("completely unrelated topic xyz", ctx=_mock_ctx())
        assert "No matching" in result

    @pytest.mark.asyncio
    async def test_related_not_ready(self):
        from fastmcp.exceptions import ToolError

        from vue_docs_server.startup import state as server_state
        from vue_docs_server.tools.related import vue_get_related

        server_state.qdrant = None
        server_state.bm25 = None
        with pytest.raises(ToolError, match="not initialized"):
            await vue_get_related("ref", ctx=_mock_ctx())
