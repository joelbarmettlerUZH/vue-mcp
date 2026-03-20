"""Tests for core Pydantic models."""

from vue_docs_core.models import (
    ApiEntity,
    Chunk,
    ChunkMetadata,
    ChunkType,
    CrossReference,
    CrossRefType,
    EntityIndex,
)
from vue_docs_core.models.entity import EntityType


def test_chunk_creation():
    meta = ChunkMetadata(
        file_path="guide/essentials/computed.md",
        folder_path="guide/essentials",
        page_title="Computed Properties",
    )
    chunk = Chunk(
        chunk_id="guide/essentials/computed#basic-example",
        chunk_type=ChunkType.SECTION,
        content="## Basic Example\n\nComputed properties are ...",
        metadata=meta,
    )
    assert chunk.chunk_id == "guide/essentials/computed#basic-example"
    assert chunk.chunk_type == ChunkType.SECTION
    assert chunk.metadata.page_title == "Computed Properties"
    assert chunk.contextual_prefix == ""
    assert chunk.hype_questions == []


def test_chunk_with_enrichment():
    meta = ChunkMetadata(
        file_path="guide/essentials/computed.md",
        folder_path="guide/essentials",
        page_title="Computed Properties",
        api_style="composition",
        api_entities=["computed", "ref"],
    )
    chunk = Chunk(
        chunk_id="guide/essentials/computed#writable-computed",
        chunk_type=ChunkType.SUBSECTION,
        content="### Writable Computed\n\n...",
        metadata=meta,
        contextual_prefix="This section covers writable computed properties in Vue 3.",
        hype_questions=["how to create a writable computed property"],
    )
    assert chunk.metadata.api_style == "composition"
    assert "computed" in chunk.metadata.api_entities
    assert len(chunk.hype_questions) == 1


def test_code_block_chunk():
    meta = ChunkMetadata(
        file_path="guide/essentials/computed.md",
        folder_path="guide/essentials",
        page_title="Computed Properties",
        content_type="code",
        language_tag="vue",
        preceding_prose="Here is an example of a computed property:",
    )
    chunk = Chunk(
        chunk_id="guide/essentials/computed#basic-example-code-0",
        chunk_type=ChunkType.CODE_BLOCK,
        content="<script setup>\nimport { ref, computed } from 'vue'\n</script>",
        metadata=meta,
    )
    assert chunk.chunk_type == ChunkType.CODE_BLOCK
    assert chunk.metadata.language_tag == "vue"
    assert chunk.metadata.preceding_prose != ""


def test_api_entity():
    entity = ApiEntity(
        name="ref",
        entity_type=EntityType.COMPOSABLE,
        page_path="api/reactivity-core.md",
        section="ref()",
        related=["reactive", "unref", "isRef"],
    )
    assert entity.name == "ref"
    assert entity.entity_type == EntityType.COMPOSABLE
    assert "reactive" in entity.related


def test_entity_index():
    idx = EntityIndex(
        entities={"ref": ApiEntity(name="ref")},
        entity_to_chunks={"ref": ["chunk-1", "chunk-2"]},
    )
    assert "ref" in idx.entities
    assert len(idx.entity_to_chunks["ref"]) == 2


def test_cross_reference():
    xref = CrossReference(
        source_chunk_id="guide/essentials/computed#basic-example",
        target_path="/api/reactivity-core.html#computed",
        link_text="computed()",
        ref_type=CrossRefType.HIGH,
    )
    assert xref.ref_type == CrossRefType.HIGH


def test_chunk_type_values():
    assert ChunkType.SECTION == "section"
    assert ChunkType.HYPE_QUESTION == "hype_question"
    assert ChunkType.PAGE_SUMMARY == "page_summary"
    assert ChunkType.FOLDER_SUMMARY == "folder_summary"
