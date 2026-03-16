"""Query-related models."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field

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
    original_query: Annotated[str, Field(description="The original user query")]
    intent: Annotated[QueryIntent, Field(description="Classified intent of the query")] = (
        QueryIntent.AUTO
    )
    detected_entities: Annotated[
        list[str], Field(description="API entities detected in the query", default_factory=list)
    ]
    sub_questions: Annotated[
        list[str],
        Field(
            description="Decomposed sub-questions for multi-faceted queries", default_factory=list
        ),
    ]
    rewritten_queries: Annotated[
        list[str],
        Field(
            description="Alternative phrasings of the query for improved recall",
            default_factory=list,
        ),
    ]
    step_back_query: Annotated[
        str, Field(description="A more general version of the query for broader context")
    ] = ""


class SearchResult(BaseModel):
    chunk: Annotated[Chunk, Field(description="The matched documentation chunk")]
    score: Annotated[float, Field(description="Relevance score from retrieval")] = 0.0
    retrieval_method: Annotated[
        str, Field(description="Method used to retrieve this result (e.g., dense, sparse, entity)")
    ] = ""
