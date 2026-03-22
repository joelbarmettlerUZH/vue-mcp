"""Additional parsing tests covering entity extraction, cross-references, and sort keys.

These tests exercise pure functions with no external dependencies.
"""

import re

from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType
from vue_docs_core.models.crossref import CrossRefType
from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.crossrefs import (
    _classify_ref_type,
    _resolve_target_path,
    _sub_folder,
    _top_folder,
    build_crossref_graph,
    extract_cross_references,
)
from vue_docs_core.parsing.entities import (
    _clean_api_name,
    _split_compound_heading,
    build_entity_index,
    extract_entities_from_chunk,
)
from vue_docs_core.parsing.sort_keys import compute_sort_key, parse_sidebar_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    content: str,
    chunk_type: ChunkType = ChunkType.SECTION,
    file_path: str = "guide/essentials/computed.md",
    chunk_id: str = "guide/essentials/computed#section",
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        chunk_type=chunk_type,
        content=content,
        metadata=ChunkMetadata(
            file_path=file_path,
            folder_path=file_path.rsplit("/", 1)[0] if "/" in file_path else "",
            page_title="Test Page",
        ),
        contextual_prefix="",
    )


def _make_dictionary() -> dict[str, ApiEntity]:
    return {
        "ref": ApiEntity(name="ref", entity_type="composable"),
        "reactive": ApiEntity(name="reactive", entity_type="composable"),
        "computed": ApiEntity(name="computed", entity_type="composable"),
        "v-model": ApiEntity(name="v-model", entity_type="directive"),
        "v-for": ApiEntity(name="v-for", entity_type="directive"),
        "Transition": ApiEntity(name="Transition", entity_type="component"),
        "defineProps": ApiEntity(name="defineProps", entity_type="compiler_macro"),
        "defineEmits": ApiEntity(name="defineEmits", entity_type="compiler_macro"),
    }


# ---------------------------------------------------------------------------
# Tests: _clean_api_name (Gap 7)
# ---------------------------------------------------------------------------


class TestCleanApiName:
    def test_simple_name(self):
        assert _clean_api_name("ref()") == "ref"

    def test_backtick_wrapped(self):
        assert _clean_api_name("`ref()`") == "ref"

    def test_angle_bracket_component(self):
        assert _clean_api_name("<Transition>") == "Transition"

    def test_backtick_angle_bracket(self):
        assert _clean_api_name("`<Transition>`") == "Transition"

    def test_slug_suffix_stripped(self):
        assert _clean_api_name("ref() {#ref}") == "ref"

    def test_sup_tag_stripped(self):
        assert _clean_api_name("ref()<sup class='vt-badge'/>") == "ref"

    def test_compound_heading_returns_none(self):
        assert _clean_api_name("defineProps() & defineEmits()") is None

    def test_prose_heading_returns_none(self):
        assert _clean_api_name("Computed Properties") is None

    def test_directive_name(self):
        assert _clean_api_name("v-model") == "v-model"

    def test_generic_type_stripped(self):
        assert _clean_api_name("PropType\\<T>") == "PropType"

    def test_strict_mode_rejects_simple_words(self):
        assert _clean_api_name("someword", strict=True) is None

    def test_strict_mode_accepts_backtick(self):
        assert _clean_api_name("`ref()`", strict=True) == "ref"

    def test_dollar_prefix(self):
        assert _clean_api_name("$emit") == "$emit"

    def test_dunder_prefix(self):
        assert _clean_api_name("__VUE_OPTIONS_API__") == "__VUE_OPTIONS_API__"

    def test_empty_string(self):
        assert _clean_api_name("") is None

    def test_app_dot_method(self):
        assert _clean_api_name("app.component()") == "app.component"


class TestSplitCompoundHeading:
    def test_single_name(self):
        assert _split_compound_heading("ref()") == ["ref"]

    def test_compound_heading(self):
        result = _split_compound_heading("defineProps() & defineEmits()")
        assert "defineProps" in result
        assert "defineEmits" in result

    def test_no_valid_parts(self):
        assert _split_compound_heading("Some Prose Heading") == []


# ---------------------------------------------------------------------------
# Tests: extract_entities_from_chunk (Gap 7)
# ---------------------------------------------------------------------------


class TestExtractEntitiesFromChunk:
    def test_inline_backtick_match(self):
        """Backtick-wrapped code tokens are matched against the dictionary."""
        chunk = _make_chunk("Use `ref()` to create a reactive reference.")
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "ref" in entities

    def test_inline_backtick_angle_brackets(self):
        """Angle-bracket components in backticks are matched."""
        chunk = _make_chunk("Wrap content in `<Transition>`.")
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "Transition" in entities

    def test_inline_backtick_no_match(self):
        """Tokens not in the dictionary are ignored."""
        chunk = _make_chunk("Use `someRandomFunction()` for something.")
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert entities == []

    def test_import_statement_extraction(self):
        """Import statements in code blocks extract entity names."""
        chunk = _make_chunk(
            "```js\nimport { ref, reactive } from 'vue'\n```",
            chunk_type=ChunkType.CODE_BLOCK,
        )
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "ref" in entities
        assert "reactive" in entities

    def test_import_with_alias(self):
        """Import aliases are handled (import { ref as myRef })."""
        chunk = _make_chunk(
            "```js\nimport { ref as myRef } from 'vue'\n```",
            chunk_type=ChunkType.CODE_BLOCK,
        )
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "ref" in entities

    def test_directive_usage_in_code_block(self):
        """Directive usage (v-model, v-for) in code blocks is detected."""
        chunk = _make_chunk(
            '```html\n<input v-model="name" />\n```',
            chunk_type=ChunkType.CODE_BLOCK,
        )
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "v-model" in entities

    def test_custom_import_patterns(self):
        """Custom import patterns override the default vue import pattern."""
        custom_pattern = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vue-router['\"]")
        chunk = _make_chunk(
            "```js\nimport { computed } from 'vue-router'\n```",
            chunk_type=ChunkType.CODE_BLOCK,
        )
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary, import_patterns=[custom_pattern])
        assert "computed" in entities

    def test_results_sorted(self):
        """Extracted entities are returned sorted."""
        chunk = _make_chunk("Use `reactive()` and `computed()` and `ref()`.")
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert entities == sorted(entities)

    def test_case_insensitive_matching(self):
        """Entity matching is case-insensitive."""
        chunk = _make_chunk("Use `Ref()` to create a reference.")
        dictionary = _make_dictionary()
        entities = extract_entities_from_chunk(chunk, dictionary)
        assert "ref" in entities


class TestBuildEntityIndex:
    def test_builds_index_with_chunk_mapping(self):
        """build_entity_index maps entities to chunk IDs."""
        chunks = [
            _make_chunk("Use `ref()` here.", chunk_id="chunk-1"),
            _make_chunk("Use `computed()` here.", chunk_id="chunk-2"),
            _make_chunk("Use `ref()` again.", chunk_id="chunk-3"),
        ]
        dictionary = _make_dictionary()
        index = build_entity_index(chunks, dictionary)

        assert "ref" in index.entity_to_chunks
        assert "chunk-1" in index.entity_to_chunks["ref"]
        assert "chunk-3" in index.entity_to_chunks["ref"]
        assert "computed" in index.entity_to_chunks
        assert "chunk-2" in index.entity_to_chunks["computed"]

    def test_mutates_chunk_metadata(self):
        """build_entity_index sets api_entities on chunk metadata."""
        chunk = _make_chunk("Use `ref()` and `reactive()`.", chunk_id="chunk-1")
        dictionary = _make_dictionary()
        build_entity_index([chunk], dictionary)

        assert "ref" in chunk.metadata.api_entities
        assert "reactive" in chunk.metadata.api_entities


# ---------------------------------------------------------------------------
# Tests: cross-reference resolution (Gap 8)
# ---------------------------------------------------------------------------


class TestResolveTargetPath:
    def test_absolute_site_root(self):
        result = _resolve_target_path("/api/reactivity-core", "guide/essentials/computed.md")
        assert result == "api/reactivity-core"

    def test_relative_dot_dot(self):
        result = _resolve_target_path("../components/v-model.html", "guide/essentials/computed.md")
        assert result == "guide/components/v-model"

    def test_relative_dot_slash(self):
        result = _resolve_target_path("./class-and-style.html", "guide/essentials/computed.md")
        assert result == "guide/essentials/class-and-style"

    def test_bare_relative(self):
        result = _resolve_target_path("class-and-style.html", "guide/essentials/computed.md")
        assert result == "guide/essentials/class-and-style"

    def test_strips_html_extension(self):
        result = _resolve_target_path("/guide/components/props.html", "api/index.md")
        assert result == "guide/components/props"

    def test_strips_md_extension(self):
        result = _resolve_target_path("/guide/components/props.md", "api/index.md")
        assert result == "guide/components/props"

    def test_preserves_anchor(self):
        result = _resolve_target_path("/api/reactivity-core#ref", "guide/computed.md")
        assert result == "api/reactivity-core#ref"

    def test_external_link_returns_none(self):
        assert _resolve_target_path("https://vuejs.org", "guide/intro.md") is None

    def test_same_page_anchor_returns_none(self):
        assert _resolve_target_path("#some-section", "guide/intro.md") is None

    def test_mailto_returns_none(self):
        assert _resolve_target_path("mailto:test@example.com", "guide/intro.md") is None

    def test_strips_trailing_slash(self):
        result = _resolve_target_path("/guide/components/", "api/index.md")
        assert result == "guide/components"


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

    def test_same_subfolder_is_medium(self):
        assert (
            _classify_ref_type("guide/essentials/computed.md", "guide/essentials/class-and-style")
            == CrossRefType.MEDIUM
        )

    def test_cross_folder_is_low(self):
        assert (
            _classify_ref_type("guide/essentials/computed.md", "guide/components/props")
            == CrossRefType.LOW
        )

    def test_same_top_different_sub_is_low(self):
        assert (
            _classify_ref_type("guide/essentials/computed.md", "guide/scaling-up/routing")
            == CrossRefType.LOW
        )


class TestExtractCrossReferences:
    def test_extracts_internal_links(self):
        chunk = _make_chunk(
            "See [Reactivity API](/api/reactivity-core) for details.",
            file_path="guide/essentials/computed.md",
        )
        refs = extract_cross_references(chunk)
        assert len(refs) == 1
        assert refs[0].target_path == "api/reactivity-core"
        assert refs[0].ref_type == CrossRefType.HIGH

    def test_deduplicates_within_chunk(self):
        chunk = _make_chunk(
            "See [ref](/api/reactivity-core) and also [reactive](/api/reactivity-core).",
            file_path="guide/essentials/computed.md",
        )
        refs = extract_cross_references(chunk)
        assert len(refs) == 1

    def test_skips_external_links(self):
        chunk = _make_chunk(
            "See [Vue](https://vuejs.org) and [ref](/api/reactivity-core).",
            file_path="guide/essentials/computed.md",
        )
        refs = extract_cross_references(chunk)
        assert len(refs) == 1
        assert refs[0].target_path == "api/reactivity-core"

    def test_skips_same_page_anchors(self):
        chunk = _make_chunk(
            "See [above](#introduction).",
            file_path="guide/essentials/computed.md",
        )
        refs = extract_cross_references(chunk)
        assert len(refs) == 0


class TestBuildCrossrefGraph:
    def test_builds_graph_and_updates_metadata(self):
        chunks = [
            _make_chunk(
                "See [ref](/api/reactivity-core) for details.",
                file_path="guide/essentials/computed.md",
                chunk_id="guide/essentials/computed#section",
            ),
            _make_chunk(
                "No links here.",
                file_path="api/reactivity-core.md",
                chunk_id="api/reactivity-core#section",
            ),
        ]
        graph = build_crossref_graph(chunks)

        assert "guide/essentials/computed#section" in graph
        assert "api/reactivity-core#section" not in graph
        assert chunks[0].metadata.cross_references == ["api/reactivity-core"]
        assert chunks[1].metadata.cross_references == []


class TestTopFolderSubFolder:
    def test_top_folder(self):
        assert _top_folder("guide/essentials/computed") == "guide"

    def test_top_folder_no_slash(self):
        assert _top_folder("api") == "api"

    def test_sub_folder(self):
        assert _sub_folder("guide/essentials/computed") == "guide/essentials"

    def test_sub_folder_short(self):
        assert _sub_folder("api") == "api"


# ---------------------------------------------------------------------------
# Tests: sort key parsing (Gap 9)
# ---------------------------------------------------------------------------


class TestParseSidebarConfig:
    def test_basic_sidebar(self, tmp_path):
        config = tmp_path / "config.ts"
        config.write_text(
            """
export default {
  themeConfig: {
    sidebar: {
      '/guide/': [
        {
          text: 'Getting Started',
          items: [
            { text: 'Introduction', link: '/guide/introduction' },
            { text: 'Quick Start', link: '/guide/quick-start' },
          ]
        },
        {
          text: 'Essentials',
          items: [
            { text: 'Reactivity', link: '/guide/essentials/reactivity-fundamentals' },
            { text: 'Computed', link: '/guide/essentials/computed' },
          ]
        }
      ],
      '/api/': [
        {
          text: 'Global API',
          items: [
            { text: 'Application', link: '/api/application' },
          ]
        }
      ]
    }
  }
}
""",
            encoding="utf-8",
        )

        result = parse_sidebar_config(config)

        # Guide section (index 0)
        assert result["guide/introduction"] == "00_00_00"
        assert result["guide/quick-start"] == "00_00_01"
        assert result["guide/essentials/reactivity-fundamentals"] == "00_01_00"
        assert result["guide/essentials/computed"] == "00_01_01"

        # API section (index 1)
        assert result["api/application"] == "01_00_00"

    def test_html_extension_stripped(self, tmp_path):
        config = tmp_path / "config.ts"
        config.write_text(
            """
{
  '/guide/': [
    {
      items: [
        { link: '/guide/intro.html' },
      ]
    }
  ]
}
""",
            encoding="utf-8",
        )

        result = parse_sidebar_config(config)
        assert "guide/intro" in result

    def test_anchor_stripped(self, tmp_path):
        config = tmp_path / "config.ts"
        config.write_text(
            """
{
  '/guide/': [
    {
      items: [
        { link: '/guide/intro#getting-started' },
      ]
    }
  ]
}
""",
            encoding="utf-8",
        )

        result = parse_sidebar_config(config)
        assert "guide/intro" in result


class TestComputeSortKey:
    def test_found_in_sidebar(self):
        sidebar_map = {"guide/essentials/computed": "00_01_02"}
        assert compute_sort_key("guide/essentials/computed.md", sidebar_map) == "00_01_02"

    def test_not_in_sidebar_fallback(self):
        sidebar_map = {}
        result = compute_sort_key("guide/extras/teleport.md", sidebar_map)
        assert result == "99_guide/extras/teleport"

    def test_md_extension_stripped(self):
        sidebar_map = {"api/index": "01_00_00"}
        assert compute_sort_key("api/index.md", sidebar_map) == "01_00_00"
