"""Tests for the markdown parser.

Option A parser: section-only chunking. H2 sections are the primary retrieval
unit. Code blocks and subsection headings stay inline. Large sections are split
at H3 boundaries.
"""

from pathlib import Path

import pytest

from vue_docs_core.models.chunk import ChunkType
from vue_docs_core.parsing.markdown import (
    _build_api_style_map,
    _extract_headings,
    _extract_slug,
    parse_markdown_file,
)

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "vue-docs" / "src"
COMPUTED_MD = DOCS_ROOT / "guide" / "essentials" / "computed.md"
LIFECYCLE_MD = DOCS_ROOT / "guide" / "essentials" / "lifecycle.md"


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


class TestExtractSlug:
    def test_with_explicit_slug(self):
        text, slug = _extract_slug("Basic Example {#basic-example}")
        assert text == "Basic Example"
        assert slug == "basic-example"

    def test_with_parens_in_title(self):
        text, slug = _extract_slug("ref() {#ref}")
        assert text == "ref()"
        assert slug == "ref"

    def test_auto_generated_slug(self):
        text, slug = _extract_slug("Some Heading Without Slug")
        assert text == "Some Heading Without Slug"
        assert slug == "some-heading-without-slug"

    def test_empty_string(self):
        text, slug = _extract_slug("")
        assert text == ""
        assert slug == ""


class TestExtractHeadings:
    def test_computed_md_headings(self):
        from markdown_it import MarkdownIt

        raw = COMPUTED_MD.read_text()
        tokens = MarkdownIt().parse(raw)
        headings = _extract_headings(tokens)

        assert headings[0].level == 1
        assert headings[0].text == "Computed Properties"
        assert headings[0].slug == "computed-properties"

        h2_texts = [h.text for h in headings if h.level == 2]
        assert "Basic Example" in h2_texts
        assert "Computed Caching vs. Methods" in h2_texts
        assert "Writable Computed" in h2_texts
        assert "Best Practices" in h2_texts

        h3_texts = [h.text for h in headings if h.level == 3]
        assert "Getters should be side-effect free" in h3_texts
        assert "Avoid mutating computed value" in h3_texts


class TestBuildApiStyleMap:
    def test_simple_options_block(self):
        lines = [
            "some text",
            '<div class="options-api">',
            "options content",
            "</div>",
            "after",
        ]
        result = _build_api_style_map(lines)
        assert result == ["both", "options", "options", "both", "both"]

    def test_composition_block(self):
        lines = [
            '<div class="composition-api">',
            "comp content",
            "</div>",
        ]
        result = _build_api_style_map(lines)
        assert result == ["composition", "composition", "both"]

    def test_sequential_blocks(self):
        lines = [
            '<div class="options-api">',
            "opts",
            "</div>",
            '<div class="composition-api">',
            "comp",
            "</div>",
        ]
        result = _build_api_style_map(lines)
        assert result == ["options", "options", "both", "composition", "composition", "both"]

    def test_no_api_blocks(self):
        lines = ["plain text", "more text"]
        result = _build_api_style_map(lines)
        assert result == ["both", "both"]


# ---------------------------------------------------------------------------
# Integration tests on real Vue docs
# ---------------------------------------------------------------------------


@pytest.fixture
def computed_chunks():
    return parse_markdown_file(COMPUTED_MD, DOCS_ROOT)


@pytest.fixture
def lifecycle_chunks():
    return parse_markdown_file(LIFECYCLE_MD, DOCS_ROOT)


class TestParseComputedMd:
    def test_page_title(self, computed_chunks):
        sections = [c for c in computed_chunks if c.chunk_type == ChunkType.SECTION]
        assert sections[0].metadata.page_title == "Computed Properties"

    def test_section_count(self, computed_chunks):
        sections = [c for c in computed_chunks if c.chunk_type == ChunkType.SECTION]
        assert len(sections) == 5
        slugs = [c.chunk_id.split("#")[1] for c in sections]
        assert "basic-example" in slugs
        assert "computed-caching-vs-methods" in slugs
        assert "writable-computed" in slugs
        assert "previous" in slugs
        assert "best-practices" in slugs

    def test_no_code_block_chunks(self, computed_chunks):
        """Option A: code blocks are inline in sections, not separate chunks."""
        cbs = [c for c in computed_chunks if c.chunk_type == ChunkType.CODE_BLOCK]
        assert len(cbs) == 0

    def test_sections_contain_code(self, computed_chunks):
        """Code blocks are embedded in the section content."""
        basic = next(c for c in computed_chunks if "basic-example" in c.chunk_id)
        assert "```js" in basic.content
        assert "computed:" in basic.content or "computed(" in basic.content

    def test_api_divs_stripped(self, computed_chunks):
        """<div class="options-api/composition-api"> markup should be stripped."""
        for c in computed_chunks:
            assert '<div class="options-api">' not in c.content
            assert '<div class="composition-api">' not in c.content

    def test_api_style_detected(self, computed_chunks):
        """Despite stripped divs, api_style metadata should be set correctly."""
        sections = [c for c in computed_chunks if c.chunk_type == ChunkType.SECTION]
        styles = {c.metadata.api_style for c in sections}
        assert "both" in styles  # most sections have both

    def test_playground_links_stripped(self, computed_chunks):
        """Playground links should be removed from content."""
        for c in computed_chunks:
            assert "play.vuejs.org" not in c.content

    def test_small_section_not_split(self, computed_chunks):
        """Best Practices (1080 chars) should NOT be split into subsections."""
        bp = next(c for c in computed_chunks if "best-practices" in c.chunk_id)
        assert bp.chunk_type == ChunkType.SECTION
        # H3 content should be inline
        assert "Getters should be side-effect free" in bp.content
        assert "Avoid mutating computed value" in bp.content

    def test_section_breadcrumbs(self, computed_chunks):
        sections = [c for c in computed_chunks if c.chunk_type == ChunkType.SECTION]
        for sec in sections:
            assert sec.metadata.breadcrumb.startswith("Computed Properties > ")

    def test_section_siblings(self, computed_chunks):
        sections = [c for c in computed_chunks if c.chunk_type == ChunkType.SECTION]
        for sec in sections:
            assert len(sec.metadata.sibling_chunk_ids) == 4  # 5 sections - 1

    def test_file_path_metadata(self, computed_chunks):
        for chunk in computed_chunks:
            assert chunk.metadata.file_path == "guide/essentials/computed.md"
            assert chunk.metadata.folder_path == "guide/essentials"

    def test_content_hash_populated(self, computed_chunks):
        for chunk in computed_chunks:
            assert chunk.content_hash != ""
            assert len(chunk.content_hash) == 16


class TestParseLifecycleMd:
    def test_has_image_chunk(self, lifecycle_chunks):
        imgs = [c for c in lifecycle_chunks if c.chunk_type == ChunkType.IMAGE]
        assert len(imgs) == 1
        assert "lifecycle.png" in imgs[0].content
        assert imgs[0].metadata.content_type == "image"

    def test_image_has_context(self, lifecycle_chunks):
        img = next(c for c in lifecycle_chunks if c.chunk_type == ChunkType.IMAGE)
        assert img.metadata.preceding_prose != ""

    def test_section_count(self, lifecycle_chunks):
        sections = [c for c in lifecycle_chunks if c.chunk_type == ChunkType.SECTION]
        assert len(sections) == 2  # Registering Lifecycle Hooks, Lifecycle Diagram


class TestLargeSectionSplitting:
    """Test that sections > 3000 chars with H3s get split."""

    def test_props_page_splits_large_sections(self):
        props_md = DOCS_ROOT / "guide" / "components" / "props.md"
        chunks = parse_markdown_file(props_md, DOCS_ROOT)
        subs = [c for c in chunks if c.chunk_type == ChunkType.SUBSECTION]
        # Prop Passing Details is >3000 chars with H3s, should split
        assert len(subs) > 0

    def test_subsection_has_intro_prepended(self):
        props_md = DOCS_ROOT / "guide" / "components" / "props.md"
        chunks = parse_markdown_file(props_md, DOCS_ROOT)
        subs = [c for c in chunks if c.chunk_type == ChunkType.SUBSECTION]
        # First subsection should start with the H2 heading
        first_sub = subs[0]
        assert first_sub.content.startswith("##")

    def test_h4_not_split(self):
        """H4 headings should stay inline, not create separate chunks."""
        props_md = DOCS_ROOT / "guide" / "components" / "props.md"
        chunks = parse_markdown_file(props_md, DOCS_ROOT)
        # "Number", "Boolean", "Array", "Object" are H4s — should NOT be chunks
        chunk_ids = {c.chunk_id for c in chunks}
        assert "guide/components/props#number" not in chunk_ids
        assert "guide/components/props#boolean" not in chunk_ids

    def test_near_empty_parent_not_emitted(self):
        """If a section's intro is tiny, skip the parent section chunk."""
        props_md = DOCS_ROOT / "guide" / "components" / "props.md"
        chunks = parse_markdown_file(props_md, DOCS_ROOT)
        # "Prop Passing Details" has almost no intro
        prop_passing = [c for c in chunks if c.chunk_id == "guide/components/props#prop-passing-details"]
        # Should either not exist, or have meaningful content
        if prop_passing:
            assert len(prop_passing[0].content) >= 100

    def test_subsection_parent_id(self):
        props_md = DOCS_ROOT / "guide" / "components" / "props.md"
        chunks = parse_markdown_file(props_md, DOCS_ROOT)
        subs = [c for c in chunks if c.chunk_type == ChunkType.SUBSECTION]
        for sub in subs:
            assert sub.metadata.parent_chunk_id != ""


class TestEdgeCases:
    def test_file_without_h2(self):
        """Files with only H1 or no headings should still produce chunks."""
        index_md = DOCS_ROOT / "index.md"
        if index_md.exists():
            chunks = parse_markdown_file(index_md, DOCS_ROOT)
            assert len(chunks) >= 1

    def test_api_reference_file(self):
        api_file = DOCS_ROOT / "api" / "reactivity-core.md"
        chunks = parse_markdown_file(api_file, DOCS_ROOT)
        sections = [c for c in chunks if c.chunk_type == ChunkType.SECTION]
        slugs = [c.chunk_id.split("#")[1] for c in sections]
        assert "ref" in slugs
        assert "computed" in slugs
        assert "reactive" in slugs

    def test_api_sections_contain_code_inline(self):
        """API reference sections should have type signatures inline."""
        api_file = DOCS_ROOT / "api" / "reactivity-core.md"
        chunks = parse_markdown_file(api_file, DOCS_ROOT)
        ref_section = next(c for c in chunks if c.chunk_id.endswith("#ref"))
        assert "```ts" in ref_section.content
        assert "function ref<T>" in ref_section.content


class TestContentCleaning:
    def test_collapsed_blank_lines(self):
        """Multiple consecutive blank lines should be collapsed to 2."""
        from vue_docs_core.parsing.markdown import _clean_section_content

        lines = ["# Heading", "", "", "", "", "Content"]
        result = _clean_section_content(lines, 0, len(lines))
        assert "\n\n\n" not in result
        assert "Content" in result

    def test_api_divs_removed(self):
        from vue_docs_core.parsing.markdown import _clean_section_content

        lines = [
            "Intro text",
            '<div class="options-api">',
            "Options content",
            "</div>",
            '<div class="composition-api">',
            "Composition content",
            "</div>",
            "After",
        ]
        result = _clean_section_content(lines, 0, len(lines))
        assert "options-api" not in result
        assert "composition-api" not in result
        assert "Options content" in result
        assert "Composition content" in result
        assert "After" in result

    def test_playground_link_removed(self):
        from vue_docs_core.parsing.markdown import _clean_section_content

        lines = [
            "Some text.",
            "[Try it in the Playground](https://play.vuejs.org/#abc123)",
            "More text.",
        ]
        result = _clean_section_content(lines, 0, len(lines))
        assert "play.vuejs.org" not in result
        assert "Some text." in result
        assert "More text." in result
