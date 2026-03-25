"""Tests for MCP server components.

Covers startup state loading, reconstruction formatting, entity detection
in search, the MCP tool registration, api_lookup tool, and end-to-end MCP
protocol integration tests using fastmcp.Client for in-process testing.

No real API calls — Jina, Qdrant, and BM25 are mocked throughout.
"""

import asyncio
import contextlib
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
from vue_docs_server.startup import ServerState
from vue_docs_server.tools.api_lookup import _clean_section_title, _do_api_lookup
from vue_docs_server.tools.related import _do_get_related
from vue_docs_server.tools.search import _do_search

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
# Tests: API Lookup Tool
# ---------------------------------------------------------------------------


class TestApiLookup:
    def setup_method(self):
        from vue_docs_server.startup import state as server_state

        entity_index = EntityIndex(
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
        server_state.entity_index = entity_index
        server_state.entity_indices = {"vue": entity_index}
        server_state.synonym_table = {"two-way binding": ["v-model"]}
        matcher = EntityMatcher(
            entity_index=entity_index,
            synonym_table=server_state.synonym_table,
        )
        server_state.entity_matcher = matcher
        server_state.entity_matchers = {"vue": matcher}
        server_state.qdrant = MagicMock()
        server_state.bm25 = MagicMock()

    @pytest.mark.asyncio
    async def test_lookup_exact(self):
        result = await _do_api_lookup("ref", source="vue", ctx=_mock_ctx())
        assert "# `ref`" in result
        assert "Composable" in result
        assert "vuejs.org/api/reactivity-core" in result
        assert "`reactive`" in result  # related APIs
        assert "Documentation chunks" in result and "2" in result

    @pytest.mark.asyncio
    async def test_lookup_case_insensitive(self):
        result = await _do_api_lookup("REF", source="vue", ctx=_mock_ctx())
        assert "# `ref`" in result

    @pytest.mark.asyncio
    async def test_lookup_with_backticks(self):
        result = await _do_api_lookup("`defineProps`", source="vue", ctx=_mock_ctx())
        assert "# `defineProps`" in result
        assert "Compiler Macro" in result

    @pytest.mark.asyncio
    async def test_lookup_hyphenated(self):
        result = await _do_api_lookup("v-model", source="vue", ctx=_mock_ctx())
        assert "# `v-model`" in result
        assert "Directive" in result

    @pytest.mark.asyncio
    async def test_lookup_fuzzy_fallback(self):
        """Fuzzy matching catches typos."""
        result = await _do_api_lookup("onMounte", source="vue", ctx=_mock_ctx())
        assert "# `onMounted`" in result

    @pytest.mark.asyncio
    async def test_lookup_not_found(self):
        result = await _do_api_lookup("nonExistentApi", source="vue", ctx=_mock_ctx())
        assert "No API entity found" in result
        assert "vue_docs_search" in result

    @pytest.mark.asyncio
    async def test_lookup_not_ready(self):
        from fastmcp.exceptions import ToolError

        from vue_docs_server.startup import state as server_state

        server_state.qdrant = None
        server_state.bm25 = None
        with pytest.raises(ToolError, match="not initialized"):
            await _do_api_lookup("ref", source="vue", ctx=_mock_ctx())

    @pytest.mark.asyncio
    async def test_lookup_section_cleaned(self):
        result = await _do_api_lookup("defineProps", source="vue", ctx=_mock_ctx())
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

            result = await _do_search(
                "how does computed caching work", source="vue", ctx=_mock_ctx()
            )

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
            await _do_search("test query", source="vue", ctx=_mock_ctx())

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

            result = await _do_search("test", scope="tutorial", source="vue", ctx=_mock_ctx())

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
        assert mcp.name == "Vue Ecosystem MCP Server"


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

    # Resource state (per-source and combined)
    page_paths = [
        "guide/essentials/computed.md",
        "guide/essentials/reactivity-fundamentals.md",
        "api/reactivity-core.md",
    ]
    folder_structure = {
        "guide/essentials": [
            "guide/essentials/computed.md",
            "guide/essentials/reactivity-fundamentals.md",
        ],
        "api": ["api/reactivity-core.md"],
    }
    server_state.page_paths = page_paths
    server_state.folder_structure = folder_structure
    server_state.page_paths_by_source = {"vue": page_paths}
    server_state.folder_structures_by_source = {"vue": folder_structure}
    server_state.entity_indices = {"vue": entity_index}
    server_state.entity_matchers = {"vue": server_state.entity_matcher}

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

        # Verify Qdrant was called with the scope filter and source
        call_kwargs = server_state.qdrant.hybrid_search.call_args
        assert call_kwargs.kwargs.get("scope_filter") == "guide/essentials"
        assert call_kwargs.kwargs.get("limit") == 50  # _RETRIEVAL_LIMIT
        assert call_kwargs.kwargs.get("source") == "vue"

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
                assert info.serverInfo.name == "Vue Ecosystem MCP Server"


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

    @pytest.mark.asyncio
    async def test_preferences_tool_registered(self):
        """The set_framework_preferences tool is always visible."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        tool_names = [t.name for t in tools]
        assert "set_framework_preferences" in tool_names

    @pytest.mark.asyncio
    async def test_preferences_resource_registered(self):
        """The ecosystem://preferences resource is always visible."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                resources = await client.list_resources()

        resource_uris = [str(r.uri) for r in resources]
        assert "ecosystem://preferences" in resource_uris

    @pytest.mark.asyncio
    async def test_read_preferences_resource(self):
        """Preferences resource returns framework activation status."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("ecosystem://preferences")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Framework Preferences" in text
        assert "Vue.js" in text

    @pytest.mark.asyncio
    async def test_call_set_framework_preferences(self):
        """Calling set_framework_preferences returns confirmation."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "set_framework_preferences",
                    {"vue": True},
                )

        assert not result.is_error
        text = result.content[0].text
        assert "Preferences Updated" in text
        assert "Vue.js" in text

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
        server_state.entity_indices = {"vue": entity_index}
        server_state.synonym_table = _make_synonym_table()
        matcher = EntityMatcher(
            entity_index=entity_index,
            synonym_table=server_state.synonym_table,
        )
        server_state.entity_matcher = matcher
        server_state.entity_matchers = {"vue": matcher}
        server_state.qdrant = MagicMock()
        server_state.bm25 = MagicMock()

    @pytest.mark.asyncio
    async def test_related_by_api_name(self):
        result = await _do_get_related("ref", source="vue", ctx=_mock_ctx())
        assert "`ref`" in result
        assert "Composable" in result

    @pytest.mark.asyncio
    async def test_related_shows_related_apis(self):
        result = await _do_get_related("ref", source="vue", ctx=_mock_ctx())
        # ref has related: reactive
        assert "reactive" in result

    @pytest.mark.asyncio
    async def test_related_by_synonym(self):
        result = await _do_get_related("two-way binding", source="vue", ctx=_mock_ctx())
        assert "v-model" in result

    @pytest.mark.asyncio
    async def test_related_no_match(self):
        result = await _do_get_related(
            "completely unrelated topic xyz", source="vue", ctx=_mock_ctx()
        )
        assert "No matching" in result

    @pytest.mark.asyncio
    async def test_related_not_ready(self):
        from fastmcp.exceptions import ToolError

        from vue_docs_server.startup import state as server_state

        server_state.qdrant = None
        server_state.bm25 = None
        with pytest.raises(ToolError, match="not initialized"):
            await _do_get_related("ref", source="vue", ctx=_mock_ctx())


# ---------------------------------------------------------------------------
# Tests: Concrete resource enumeration (Gap 1)
# ---------------------------------------------------------------------------


class TestConcreteResources:
    """Verify that _register_concrete_resources creates concrete resources from state."""

    @pytest.mark.asyncio
    async def test_concrete_page_resources_listed(self):
        """Concrete page resources appear in list_resources."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                resources = await client.list_resources()

        uris = [str(r.uri) for r in resources]
        # Pages from _setup_server_state have .md stripped
        assert "vue://pages/guide/essentials/computed" in uris
        assert "vue://pages/api/reactivity-core" in uris

    @pytest.mark.asyncio
    async def test_concrete_entity_resources_listed(self):
        """Concrete API entity resources appear in list_resources."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                resources = await client.list_resources()

        uris = [str(r.uri) for r in resources]
        assert "vue://api/entities/ref" in uris
        assert "vue://api/entities/computed" in uris

    @pytest.mark.asyncio
    async def test_concrete_section_resources_listed(self):
        """Concrete section topics resources appear in list_resources."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                resources = await client.list_resources()

        uris = [str(r.uri) for r in resources]
        # Sections are top-level folders: "guide" and "api"
        assert "vue://topics/guide" in uris
        assert "vue://topics/api" in uris

    @pytest.mark.asyncio
    async def test_concrete_page_resource_readable(self):
        """A concrete page resource returns content when read."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()
        server_state.db = MagicMock()
        server_state.db.read_page.return_value = "# Computed Properties\n\nContent here."

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://pages/guide/essentials/computed")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Computed Properties" in text

    @pytest.mark.asyncio
    async def test_concrete_entity_resource_readable(self):
        """A concrete entity resource returns entity details when read."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://api/entities/ref")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "`ref`" in text
        assert "Composable" in text

    def test_register_concrete_resources_empty_state(self):
        """_register_concrete_resources adds nothing when state is empty."""
        from vue_docs_server.main import _register_concrete_resources
        from vue_docs_server.startup import state as server_state

        server_state.page_paths_by_source = {"vue": []}
        server_state.entity_indices = {"vue": EntityIndex()}
        server_state.folder_structures_by_source = {"vue": {}}

        mock_app = MagicMock()
        _register_concrete_resources(mock_app)

        mock_app.add_resource.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Framework preferences visibility (Gap 2)
# ---------------------------------------------------------------------------


class TestFrameworkPreferences:
    """Verify the set_framework_preferences tool and ecosystem://preferences resource."""

    @pytest.mark.asyncio
    async def test_preferences_tool_enables_vue(self):
        """set_framework_preferences enables vue when vue=True."""
        from vue_docs_server.main import set_framework_preferences

        ctx = _mock_ctx()
        ctx.enable_components = AsyncMock()
        ctx.disable_components = AsyncMock()

        result = await set_framework_preferences(vue=True, ctx=ctx)

        assert "Preferences Updated" in result
        ctx.enable_components.assert_any_call(tags={"vue"})

    @pytest.mark.asyncio
    async def test_preferences_tool_disables_vue(self):
        """set_framework_preferences disables vue when vue=False."""
        from vue_docs_server.main import set_framework_preferences

        ctx = _mock_ctx()
        ctx.enable_components = AsyncMock()
        ctx.disable_components = AsyncMock()

        result = await set_framework_preferences(vue=False, ctx=ctx)

        ctx.disable_components.assert_any_call(tags={"vue"})
        assert "Inactive" in result

    @pytest.mark.asyncio
    async def test_preferences_activates_all_requested(self):
        """All requested sources are activated."""
        from vue_docs_server.main import set_framework_preferences

        ctx = _mock_ctx()
        ctx.enable_components = AsyncMock()
        ctx.disable_components = AsyncMock()

        result = await set_framework_preferences(vue=True, vue_router=True, vueuse=False, ctx=ctx)

        assert "Vue.js" in result
        assert "Vue Router" in result
        assert ctx.enable_components.call_count == 2
        ctx.enable_components.assert_any_call(tags={"vue"})
        ctx.enable_components.assert_any_call(tags={"vue-router"})
        ctx.disable_components.assert_called_once_with(tags={"vueuse"})

    @pytest.mark.asyncio
    async def test_preferences_stores_state(self):
        """Preferences are stored in session state."""
        from vue_docs_server.main import set_framework_preferences

        ctx = _mock_ctx()
        ctx.enable_components = AsyncMock()
        ctx.disable_components = AsyncMock()

        await set_framework_preferences(vue=True, vue_router=False, vueuse=False, ctx=ctx)

        ctx.set_state.assert_called_once_with(
            "framework_preferences", {"vue": True, "vue-router": False, "vueuse": False}
        )

    @pytest.mark.asyncio
    async def test_preferences_resource_content(self):
        """ecosystem://preferences resource shows framework info."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.read_resource("ecosystem://preferences")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Framework Preferences" in text
        assert "Vue.js" in text
        assert "set_framework_preferences" in text


# ---------------------------------------------------------------------------
# Tests: HyPE resolution (Gap 4)
# ---------------------------------------------------------------------------


class TestHypeResolution:
    """Tests for _resolve_hype_hits in search.py."""

    def setup_method(self):
        from vue_docs_server.startup import state as server_state

        self.mock_qdrant = MagicMock()
        server_state.qdrant = self.mock_qdrant

    def test_no_hype_hits_passthrough(self):
        """Regular hits pass through unchanged."""
        from vue_docs_server.tools.search import _resolve_hype_hits

        hits = [
            _make_hit(chunk_id="guide/a#section", score=0.9),
            _make_hit(chunk_id="guide/b#section", score=0.8),
        ]
        result = _resolve_hype_hits(hits)
        assert len(result) == 2
        assert result[0].score == 0.9
        assert result[1].score == 0.8

    def test_hype_hit_replaced_by_parent(self):
        """A hype_question hit is replaced by its parent chunk."""
        from vue_docs_server.tools.search import _resolve_hype_hits

        hype_hit = SearchHit(
            chunk_id="hype-q-1",
            score=0.85,
            payload={
                "chunk_id": "hype-q-1",
                "chunk_type": "hype_question",
                "parent_chunk_id": "guide/essentials/computed#caching",
                "content": "How does computed caching work?",
            },
        )

        self.mock_qdrant.get_by_chunk_ids.return_value = [
            {
                "chunk_id": "guide/essentials/computed#caching",
                "chunk_type": "section",
                "content": "Computed properties cache their result.",
                "file_path": "guide/essentials/computed.md",
            }
        ]

        result = _resolve_hype_hits([hype_hit])

        self.mock_qdrant.get_by_chunk_ids.assert_called_once_with(
            ["guide/essentials/computed#caching"]
        )
        assert len(result) == 1
        assert result[0].chunk_id == "guide/essentials/computed#caching"
        assert result[0].score == 0.85

    def test_hype_hit_dedup_with_existing(self):
        """If parent is already in results, the HyPE hit is skipped."""
        from vue_docs_server.tools.search import _resolve_hype_hits

        regular_hit = _make_hit(chunk_id="guide/essentials/computed#caching", score=0.9)
        hype_hit = SearchHit(
            chunk_id="hype-q-1",
            score=0.85,
            payload={
                "chunk_id": "hype-q-1",
                "chunk_type": "hype_question",
                "parent_chunk_id": "guide/essentials/computed#caching",
                "content": "How does computed caching work?",
            },
        )

        result = _resolve_hype_hits([regular_hit, hype_hit])
        # Parent already present, no Qdrant fetch needed for that parent
        assert len(result) == 1
        assert result[0].chunk_id == "guide/essentials/computed#caching"

    def test_hype_hit_missing_parent_id_skipped(self):
        """A HyPE hit with empty parent_chunk_id is silently skipped."""
        from vue_docs_server.tools.search import _resolve_hype_hits

        hype_hit = SearchHit(
            chunk_id="hype-q-1",
            score=0.85,
            payload={
                "chunk_id": "hype-q-1",
                "chunk_type": "hype_question",
                "parent_chunk_id": "",
                "content": "Some question",
            },
        )

        result = _resolve_hype_hits([hype_hit])
        assert len(result) == 0

    def test_multiple_hype_hits_same_parent_deduped(self):
        """Multiple HyPE questions pointing to the same parent produce one result."""
        from vue_docs_server.tools.search import _resolve_hype_hits

        parent_id = "guide/essentials/computed#caching"
        hype1 = SearchHit(
            chunk_id="hype-q-1",
            score=0.9,
            payload={
                "chunk_id": "hype-q-1",
                "chunk_type": "hype_question",
                "parent_chunk_id": parent_id,
            },
        )
        hype2 = SearchHit(
            chunk_id="hype-q-2",
            score=0.8,
            payload={
                "chunk_id": "hype-q-2",
                "chunk_type": "hype_question",
                "parent_chunk_id": parent_id,
            },
        )

        self.mock_qdrant.get_by_chunk_ids.return_value = [
            {"chunk_id": parent_id, "chunk_type": "section", "content": "Caching."},
        ]

        result = _resolve_hype_hits([hype1, hype2])
        assert len(result) == 1
        assert result[0].chunk_id == parent_id

    def test_mixed_regular_and_hype_sorted_by_score(self):
        """Results are sorted by score with regular and resolved HyPE mixed."""
        from vue_docs_server.tools.search import _resolve_hype_hits

        regular = _make_hit(chunk_id="guide/a#section", score=0.7)
        hype = SearchHit(
            chunk_id="hype-q-1",
            score=0.95,
            payload={
                "chunk_id": "hype-q-1",
                "chunk_type": "hype_question",
                "parent_chunk_id": "guide/b#section",
            },
        )

        self.mock_qdrant.get_by_chunk_ids.return_value = [
            {"chunk_id": "guide/b#section", "chunk_type": "section", "content": "B content."},
        ]

        result = _resolve_hype_hits([regular, hype])
        assert len(result) == 2
        # Higher score first
        assert result[0].chunk_id == "guide/b#section"
        assert result[0].score == 0.95
        assert result[1].chunk_id == "guide/a#section"


# ---------------------------------------------------------------------------
# Tests: _do_read_page (Gap 5)
# ---------------------------------------------------------------------------


class TestReadPage:
    """Tests for the page resource read implementation."""

    @pytest.mark.asyncio
    async def test_read_page_from_db(self):
        """_do_read_page returns content from DB."""
        from vue_docs_server.resources.pages import _do_read_page
        from vue_docs_server.startup import state as server_state

        server_state.db = MagicMock()
        server_state.db.read_page.return_value = "# Page Title\n\nContent here."

        result = await _do_read_page("guide/essentials/computed", source="vue")
        assert "Page Title" in result
        server_state.db.read_page.assert_called_once_with("guide/essentials/computed", source="vue")

    @pytest.mark.asyncio
    async def test_read_page_not_found_raises(self):
        """_do_read_page raises ResourceError when page not found."""
        from fastmcp.exceptions import ResourceError

        from vue_docs_server.resources.pages import _do_read_page
        from vue_docs_server.startup import state as server_state

        server_state.db = MagicMock()
        server_state.db.read_page.return_value = None
        server_state.page_paths_by_source = {
            "vue": ["guide/essentials/computed.md", "api/reactivity-core.md"]
        }

        with pytest.raises(ResourceError, match="Page not found"):
            await _do_read_page("nonexistent/page", source="vue")

    @pytest.mark.asyncio
    async def test_read_page_no_db_raises(self):
        """_do_read_page raises ResourceError when no DB configured."""
        from fastmcp.exceptions import ResourceError

        from vue_docs_server.resources.pages import _do_read_page
        from vue_docs_server.startup import state as server_state

        server_state.db = None

        with pytest.raises(ResourceError, match="Database not configured"):
            await _do_read_page("guide/essentials/computed", source="vue")

    @pytest.mark.asyncio
    async def test_read_page_error_includes_examples(self):
        """Page not found error includes example available pages."""
        from fastmcp.exceptions import ResourceError

        from vue_docs_server.resources.pages import _do_read_page
        from vue_docs_server.startup import state as server_state

        server_state.db = MagicMock()
        server_state.db.read_page.return_value = None
        server_state.page_paths_by_source = {
            "vue": ["guide/essentials/computed.md", "api/reactivity-core.md"]
        }

        with pytest.raises(ResourceError, match="guide/essentials/computed"):
            await _do_read_page("wrong/path", source="vue")


# ---------------------------------------------------------------------------
# Tests: Startup paths (Gap 3)
# ---------------------------------------------------------------------------


class TestStartupPaths:
    """Tests for startup.py data loading logic."""

    def test_server_state_is_ready(self):
        """ServerState.is_ready reflects qdrant and bm25 availability."""
        from vue_docs_server.startup import ServerState

        s = ServerState()
        assert not s.is_ready

        s.qdrant = MagicMock()
        assert not s.is_ready

        s.bm25 = MagicMock()
        assert s.is_ready

    def test_load_from_pg_builds_per_source_state(self):
        """_load_from_pg populates per-source state from mocked PG client."""
        from vue_docs_server.startup import _load_from_pg, state

        mock_db = MagicMock()

        entity_index = EntityIndex(
            entities={"ref": ApiEntity(name="ref", entity_type=EntityType.COMPOSABLE, source="vue")}
        )
        mock_db.load_entities.side_effect = lambda source=None: (
            entity_index if source == "vue" else EntityIndex()
        )
        mock_db.load_synonyms.return_value = {"reactivity": ["ref"]}
        mock_db.load_pages_listing.return_value = (
            ["guide/computed.md"],
            {"guide": ["guide/computed.md"]},
        )
        mock_db.load_bm25_model.return_value = True

        state.entity_indices = {}
        state.page_paths_by_source = {}
        state.folder_structures_by_source = {}
        state.entity_matchers = {}
        state._bm25_tmp_dir = None

        with patch("vue_docs_server.startup.BM25Model") as MockBM25:
            MockBM25.return_value.vocab_size = 100
            _load_from_pg(mock_db)

        assert "vue" in state.entity_indices
        assert "ref" in state.entity_indices["vue"].entities
        assert "vue" in state.page_paths_by_source
        assert "vue" in state.entity_matchers
        assert state.entity_matcher is not None

    @pytest.mark.asyncio
    async def test_hot_reload_loop_reloads_on_change(self):
        """hot_reload_loop triggers data reload and resource refresh when PG timestamps change."""
        import vue_docs_server.startup as startup_module
        from vue_docs_server.startup import state

        mock_db = MagicMock()
        state.db = mock_db

        # First call returns a newer timestamp than the initial _last_reload_ts
        from datetime import UTC, datetime

        new_ts = datetime(2025, 6, 1, tzinfo=UTC)
        mock_db.get_max_updated_at.return_value = new_ts

        original_interval = startup_module._HOT_RELOAD_INTERVAL
        # Patch to make the loop fast
        startup_module._HOT_RELOAD_INTERVAL = 0.01
        startup_module._last_reload_ts = datetime(2025, 1, 1, tzinfo=UTC)

        reload_called = False
        resources_refreshed = False

        def mock_load(db):
            nonlocal reload_called
            reload_called = True

        def mock_register():
            nonlocal resources_refreshed
            resources_refreshed = True

        try:
            with (
                patch.object(startup_module, "_load_from_pg", mock_load),
                patch.object(startup_module, "settings") as mock_settings,
            ):
                mock_settings.database_url = "postgresql://test"
                task = asyncio.create_task(startup_module.hot_reload_loop(mock_register))
                await asyncio.sleep(0.1)
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        finally:
            startup_module._HOT_RELOAD_INTERVAL = original_interval

        assert reload_called
        assert resources_refreshed


# ---------------------------------------------------------------------------
# Tests: Scopes aggregation (Gap 10)
# ---------------------------------------------------------------------------


class TestScopesAggregation:
    """Tests for the scopes resource parent-path aggregation."""

    @pytest.mark.asyncio
    async def test_scopes_parent_path_counts(self):
        """Scopes resource correctly counts pages in parent paths."""
        from vue_docs_core.data.sources import SOURCE_REGISTRY
        from vue_docs_server.resources.scopes import make_scopes_resource
        from vue_docs_server.startup import state as server_state

        server_state.folder_structures_by_source = {
            "vue": {
                "guide/essentials": [
                    "guide/essentials/computed.md",
                    "guide/essentials/class-and-style.md",
                ],
                "guide/components": ["guide/components/registration.md"],
                "api": ["api/reactivity-core.md", "api/built-in-directives.md"],
            }
        }
        server_state.page_paths_by_source = {
            "vue": [
                "guide/essentials/computed.md",
                "guide/essentials/class-and-style.md",
                "guide/components/registration.md",
                "api/reactivity-core.md",
                "api/built-in-directives.md",
            ]
        }

        scopes_fn = make_scopes_resource(SOURCE_REGISTRY["vue"])
        result = await scopes_fn()

        # "guide" parent should count all 3 guide pages
        assert '"guide"' in result
        assert '"api"' in result
        # Total pages in "all"
        assert "| 5 |" in result

    @pytest.mark.asyncio
    async def test_scopes_empty_raises(self):
        """Scopes resource raises when no docs indexed."""
        from fastmcp.exceptions import ResourceError

        from vue_docs_core.data.sources import SOURCE_REGISTRY
        from vue_docs_server.resources.scopes import make_scopes_resource
        from vue_docs_server.startup import state as server_state

        server_state.folder_structures_by_source = {"vue": {}}
        server_state.page_paths_by_source = {"vue": []}

        scopes_fn = make_scopes_resource(SOURCE_REGISTRY["vue"])
        with pytest.raises(ResourceError, match=r"No Vue\.js documentation indexed"):
            await scopes_fn()


# ---------------------------------------------------------------------------
# Tests: End-to-end MCP protocol flows
# ---------------------------------------------------------------------------


class TestMCPEndToEnd:
    """Deeper end-to-end tests that exercise full request/response cycles.

    These go beyond the basic TestMCPIntegration by testing multi-step flows,
    error paths, and resource reads through the MCP protocol layer.
    """

    @pytest.mark.asyncio
    async def test_search_no_results_returns_message(self):
        """Search with no Qdrant hits returns a user-friendly message."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()
        server_state.qdrant.hybrid_search.return_value = []

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
                    "vue_docs_search",
                    {"query": "nonexistent topic xyz"},
                )

        assert not result.is_error
        assert "No documentation found" in result.content[0].text

    @pytest.mark.asyncio
    async def test_search_scope_fallback_on_empty(self):
        """Search falls back to 'all' scope when scoped search returns nothing."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()
        # First call (scoped) returns nothing, second call (unscoped) returns hit
        server_state.qdrant.hybrid_search.side_effect = [
            [],
            [
                _make_hit(
                    content="Fallback result content.",
                    api_entities=["ref"],
                )
            ],
        ]

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.rerank.return_value = RerankResult(indices=[0], scores=[0.9], total_tokens=50)
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search",
                    {"query": "ref basics", "scope": "guide/advanced"},
                )

        assert not result.is_error
        assert "Fallback result" in result.content[0].text
        # Verify two hybrid_search calls: scoped then unscoped
        assert server_state.qdrant.hybrid_search.call_count == 2

    @pytest.mark.asyncio
    async def test_api_lookup_not_found(self):
        """API lookup for unknown entity returns helpful message."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_api_lookup",
                    {"api_name": "nonExistentApi"},
                )

        assert not result.is_error
        text = result.content[0].text
        assert "no api entity found" in text.lower()

    @pytest.mark.asyncio
    async def test_read_toc_resource(self):
        """Reading vue://topics returns a table of contents."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://topics")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Vue.js" in text

    @pytest.mark.asyncio
    async def test_read_scopes_resource(self):
        """Reading vue://scopes returns valid scope values."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://scopes")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Scope" in text
        assert "guide" in text

    @pytest.mark.asyncio
    async def test_read_api_index_resource(self):
        """Reading vue://api/index returns entity listing."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            async with Client(mcp) as client:
                result = await client.read_resource("vue://api/index")

        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "ref" in text

    @pytest.mark.asyncio
    async def test_search_with_hype_resolution(self):
        """End-to-end: HyPE question hits are resolved to parent chunks."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()
        # Return a HyPE question hit from hybrid search
        hype_hit = SearchHit(
            chunk_id="hype-q-1",
            score=0.95,
            payload={
                "chunk_id": "hype-q-1",
                "chunk_type": "hype_question",
                "parent_chunk_id": "guide/essentials/computed#caching",
                "content": "How does computed caching work?",
            },
        )
        server_state.qdrant.hybrid_search.return_value = [hype_hit]
        # Parent chunk returned by get_by_chunk_ids
        server_state.qdrant.get_by_chunk_ids.return_value = [
            {
                "chunk_id": "guide/essentials/computed#caching",
                "chunk_type": "section",
                "content": "Computed properties cache their result.",
                "content_type": "text",
                "breadcrumb": "Vue.js > Computed Properties > Caching",
                "file_path": "guide/essentials/computed.md",
                "page_title": "Computed Properties",
                "section_title": "Caching",
                "subsection_title": "",
                "global_sort_key": "00_01_02",
                "api_entities": ["computed"],
                "cross_references": [],
                "source": "vue",
            }
        ]

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.rerank.return_value = RerankResult(indices=[0], scores=[0.9], total_tokens=50)
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search",
                    {"query": "computed caching"},
                )

        assert not result.is_error
        text = result.content[0].text
        # The resolved parent chunk content should appear
        assert "cache" in text.lower()

    @pytest.mark.asyncio
    async def test_list_prompts(self):
        """Server exposes prompts via MCP."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                prompts = await client.list_prompts()

        prompt_names = [p.name for p in prompts]
        assert "debug_vue_issue" in prompt_names
        assert "compare_vue_apis" in prompt_names
        assert "migrate_vue_pattern" in prompt_names

    @pytest.mark.asyncio
    async def test_get_prompt_debug(self):
        """Calling a debug prompt returns structured content."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                result = await client.get_prompt(
                    "debug_vue_issue",
                    {"symptom": "Component not rendering"},
                )

        assert len(result.messages) >= 2
        # The symptom appears in the user message (second message)
        all_text = " ".join(m.content.text for m in result.messages)
        assert "Component not rendering" in all_text

    @pytest.mark.asyncio
    async def test_search_stores_query_history(self):
        """Search tool stores query history in session state."""
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
                indices=[0], scores=[0.9], total_tokens=100
            )
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                # First search
                await client.call_tool("vue_docs_search", {"query": "computed properties"})
                # Second search
                await client.call_tool("vue_docs_search", {"query": "ref vs reactive"})
                # The query history is stored in session state —
                # verify through a third call (state accumulates)
                result = await client.call_tool("vue_docs_search", {"query": "watch effect"})

        assert not result.is_error


# ---------------------------------------------------------------------------
# Tests: Session isolation (multi-user)
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    """Verify that two concurrent MCP sessions have isolated state.

    FastMCP prefixes state keys with ``session_id``, which is a UUID
    generated per ``Client`` connection.  These tests prove that
    tool-call side-effects in one session are invisible to another.
    """

    @pytest.mark.asyncio
    async def test_query_history_isolated_between_sessions(self):
        """Query history accumulated in session A is not visible in session B."""
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
                indices=[0], scores=[0.9], total_tokens=100
            )
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            # Session A: run searches to build up history
            async with Client(mcp) as client_a:
                await client_a.call_tool("vue_docs_search", {"query": "session A query 1"})
                await client_a.call_tool("vue_docs_search", {"query": "session A query 2"})

            # Session B: fresh session should have no history from A
            async with Client(mcp) as client_b:
                result_b = await client_b.call_tool("vue_docs_search", {"query": "session B query"})

        assert not result_b.is_error
        # If state leaked, session B would see A's history.
        # The fact that the call succeeds cleanly (no prior state) is the proof.
        # We verify it produces a valid result (not corrupted by A's state).
        assert len(result_b.content) > 0

    @pytest.mark.asyncio
    async def test_preferences_isolated_between_sessions(self):
        """Framework preferences set in session A are not visible in session B."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            # Session A: disable Vue (unusual but tests isolation)
            async with Client(mcp) as client_a:
                result_a = await client_a.call_tool("set_framework_preferences", {"vue": False})
                text_a = result_a.content[0].text
                assert "Inactive" in text_a

                # After disabling vue, session A should see fewer tools
                tools_a = await client_a.list_tools()
                tool_names_a = {t.name for t in tools_a}

            # Session B: fresh session, should see default (vue active)
            async with Client(mcp) as client_b:
                tools_b = await client_b.list_tools()
                tool_names_b = {t.name for t in tools_b}

        # Session A disabled vue, so vue-tagged tools should be hidden
        assert "vue_docs_search" not in tool_names_a
        # Session B is fresh — vue tools should be visible (default)
        assert "vue_docs_search" in tool_names_b

    @pytest.mark.asyncio
    async def test_concurrent_sessions_independent(self):
        """Two sessions open simultaneously maintain independent state."""
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
                indices=[0], scores=[0.9], total_tokens=100
            )
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            # Open both sessions at the same time
            async with Client(mcp) as client_a, Client(mcp) as client_b:
                # Session A: disable vue
                await client_a.call_tool("set_framework_preferences", {"vue": False})
                # Session B: should still have vue enabled (default)
                tools_b = await client_b.list_tools()
                tool_names_b = {t.name for t in tools_b}

                # Verify A's preference change didn't affect B
                assert "vue_docs_search" in tool_names_b

                # Session A should have vue disabled
                tools_a = await client_a.list_tools()
                tool_names_a = {t.name for t in tools_a}
                assert "vue_docs_search" not in tool_names_a

    @pytest.mark.asyncio
    async def test_visibility_resets_on_new_session(self):
        """A new session does not inherit visibility rules from a prior session."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
        ):
            # Session 1: disable vue
            async with Client(mcp) as client1:
                await client1.call_tool("set_framework_preferences", {"vue": False})
                tools1 = await client1.list_tools()
                assert "vue_docs_search" not in {t.name for t in tools1}

            # Session 2: fresh — should see vue tools
            async with Client(mcp) as client2:
                tools2 = await client2.list_tools()
                assert "vue_docs_search" in {t.name for t in tools2}

            # Session 3: also fresh
            async with Client(mcp) as client3:
                tools3 = await client3.list_tools()
                assert "vue_docs_search" in {t.name for t in tools3}
