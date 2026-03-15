"""Tests for the markdown parser."""

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

    def test_subsection_count(self, computed_chunks):
        subs = [c for c in computed_chunks if c.chunk_type == ChunkType.SUBSECTION]
        assert len(subs) == 2
        sub_titles = [c.metadata.subsection_title for c in subs]
        assert "Getters should be side-effect free" in sub_titles
        assert "Avoid mutating computed value" in sub_titles

    def test_subsection_parent_is_best_practices(self, computed_chunks):
        subs = [c for c in computed_chunks if c.chunk_type == ChunkType.SUBSECTION]
        for sub in subs:
            assert sub.metadata.parent_chunk_id == "guide/essentials/computed#best-practices"
            assert sub.metadata.section_title == "Best Practices"

    def test_code_block_chunks(self, computed_chunks):
        cbs = [c for c in computed_chunks if c.chunk_type == ChunkType.CODE_BLOCK]
        assert len(cbs) >= 10  # many code blocks in this file

    def test_code_block_language_tags(self, computed_chunks):
        cbs = [c for c in computed_chunks if c.chunk_type == ChunkType.CODE_BLOCK]
        langs = {c.metadata.language_tag for c in cbs}
        assert "js" in langs
        assert "vue" in langs or "vue-html" in langs

    def test_code_block_api_style(self, computed_chunks):
        cbs = [c for c in computed_chunks if c.chunk_type == ChunkType.CODE_BLOCK]
        styles = {c.metadata.api_style for c in cbs}
        assert "options" in styles
        assert "composition" in styles

    def test_code_block_preceding_prose(self, computed_chunks):
        cbs = [c for c in computed_chunks if c.chunk_type == ChunkType.CODE_BLOCK]
        cbs_with_prose = [c for c in cbs if c.metadata.preceding_prose]
        assert len(cbs_with_prose) > 0

    def test_section_breadcrumbs(self, computed_chunks):
        sections = [c for c in computed_chunks if c.chunk_type == ChunkType.SECTION]
        for sec in sections:
            assert sec.metadata.breadcrumb.startswith("Computed Properties > ")

    def test_section_siblings(self, computed_chunks):
        sections = [c for c in computed_chunks if c.chunk_type == ChunkType.SECTION]
        for sec in sections:
            assert len(sec.metadata.sibling_chunk_ids) == 4  # 5 sections - 1

    def test_section_children(self, computed_chunks):
        bp = next(
            c for c in computed_chunks
            if c.chunk_type == ChunkType.SECTION
            and c.chunk_id.endswith("#best-practices")
        )
        assert "guide/essentials/computed#getters-should-be-side-effect-free" in bp.metadata.child_chunk_ids
        assert "guide/essentials/computed#avoid-mutating-computed-value" in bp.metadata.child_chunk_ids

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


class TestEdgeCases:
    def test_file_without_h2(self):
        """Files with only H1 or no headings should still produce chunks."""
        # The index.md file may not have H2 headings
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
