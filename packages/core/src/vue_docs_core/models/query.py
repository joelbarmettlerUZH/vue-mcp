"""Query-related models."""

from enum import Enum

from pydantic import BaseModel

from vue_docs_core.models.chunk import Chunk


class QueryIntent(str, Enum):
    API_LOOKUP = "api_lookup"
    CONCEPTUAL = "conceptual"
    HOWTO = "howto"
    DEBUGGING = "debugging"
    COMPARISON = "comparison"
    MIGRATION = "migration"
    AUTO = "auto"


class QueryTransformResult(BaseModel):
    original_query: str
    intent: QueryIntent = QueryIntent.AUTO
    detected_entities: list[str] = []
    sub_questions: list[str] = []
    rewritten_queries: list[str] = []
    step_back_query: str = ""


class SearchResult(BaseModel):
    chunk: Chunk
    score: float = 0.0
    retrieval_method: str = ""
