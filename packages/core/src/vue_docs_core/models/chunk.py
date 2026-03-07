"""Chunk and chunk metadata models."""

from enum import Enum

from pydantic import BaseModel


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
    file_path: str
    folder_path: str
    page_title: str
    section_title: str = ""
    subsection_title: str = ""
    breadcrumb: str = ""
    global_sort_key: str = ""
    content_type: str = "text"
    language_tag: str = ""
    api_style: str = "both"  # "composition", "options", "both"
    api_entities: list[str] = []
    cross_references: list[str] = []
    parent_chunk_id: str = ""
    sibling_chunk_ids: list[str] = []
    child_chunk_ids: list[str] = []
    preceding_prose: str = ""


class Chunk(BaseModel):
    chunk_id: str
    chunk_type: ChunkType
    content: str
    metadata: ChunkMetadata
    contextual_prefix: str = ""
    hype_questions: list[str] = []
    content_hash: str = ""
