"""Chunk and chunk metadata models."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    SECTION = "section"
    SUBSECTION = "subsection"
    CODE_BLOCK = "code_block"
    IMAGE = "image"
    PAGE_SUMMARY = "page_summary"
    FOLDER_SUMMARY = "folder_summary"
    TOP_SUMMARY = "top_summary"
    HYPE_QUESTION = "hype_question"


class ChunkMetadata(BaseModel):
    source: Annotated[
        str, Field(description="Source framework identifier (e.g. 'vue', 'nuxt')")
    ] = "vue"
    file_path: Annotated[str, Field(description="Relative path to the source markdown file")]
    folder_path: Annotated[str, Field(description="Folder containing the source file")]
    page_title: Annotated[str, Field(description="Title of the documentation page")]
    section_title: Annotated[str, Field(description="Title of the H2 section")] = ""
    subsection_title: Annotated[str, Field(description="Title of the H3 subsection")] = ""
    breadcrumb: Annotated[str, Field(description="Full breadcrumb path for display")] = ""
    global_sort_key: Annotated[
        str, Field(description="Sort key encoding position in the documentation hierarchy")
    ] = ""
    content_type: Annotated[str, Field(description="Type of content: text, code, or image")] = (
        "text"
    )
    language_tag: Annotated[
        str, Field(description="Language tag for code blocks (e.g., js, ts, vue)")
    ] = ""
    api_style: Annotated[str, Field(description="API style: composition, options, or both")] = (
        "both"
    )
    api_entities: Annotated[
        list[str],
        Field(
            description="List of API entity names referenced in this chunk", default_factory=list
        ),
    ]
    cross_references: Annotated[
        list[str], Field(description="List of cross-reference target paths", default_factory=list)
    ]
    parent_chunk_id: Annotated[
        str, Field(description="ID of the parent chunk in the hierarchy")
    ] = ""
    sibling_chunk_ids: Annotated[
        list[str],
        Field(description="IDs of sibling chunks at the same level", default_factory=list),
    ]
    child_chunk_ids: Annotated[
        list[str], Field(description="IDs of child chunks under this chunk", default_factory=list)
    ]
    preceding_prose: Annotated[
        str, Field(description="Prose text preceding a code block or image")
    ] = ""


class Chunk(BaseModel):
    chunk_id: Annotated[
        str, Field(description="Unique identifier derived from file path and heading")
    ]
    chunk_type: Annotated[
        ChunkType, Field(description="Type of chunk: section, subsection, code_block, etc.")
    ]
    content: Annotated[str, Field(description="Raw content text of the chunk")]
    metadata: Annotated[ChunkMetadata, Field(description="Structural and contextual metadata")]
    contextual_prefix: Annotated[
        str, Field(description="LLM-generated context prefix for embedding enrichment")
    ] = ""
    hype_questions: Annotated[
        list[str],
        Field(
            description="Hypothetical developer questions this chunk answers", default_factory=list
        ),
    ]
    content_hash: Annotated[
        str, Field(description="SHA-256 hash prefix of the content for change detection")
    ] = ""
