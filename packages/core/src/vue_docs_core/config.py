"""Application configuration via environment variables and constants."""

from pydantic_settings import BaseSettings
from qdrant_client.models import PayloadSchemaType


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Jina AI
    jina_api_key: str = ""
    jina_embedding_model: str = "jina-embeddings-v5-text-small"
    jina_reranker_model: str = "jina-reranker-v3"
    jina_embedding_dimensions: int = 1024

    # Gemini
    gemini_api_key: str = ""
    gemini_flash_model: str = "gemini-2.5-flash"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "vue_ecosystem"

    # Paths
    data_path: str = "./data"

    # Sources (empty = all registered sources)
    enabled_sources: str = ""

    # Server
    server_transport: str = "stdio"
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    mask_error_details: bool = False

    # Database
    database_url: str = ""

    # Pipeline
    pipeline_version: str = "6"  # Bumped: Multi-framework source support


settings = Settings()

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

JINA_EMBEDDING_URL = "https://api.jina.ai/v1/embeddings"
JINA_RERANKER_URL = "https://api.jina.ai/v1/rerank"

# ---------------------------------------------------------------------------
# Jina task types for jina-embeddings-v4+
# ---------------------------------------------------------------------------

TASK_RETRIEVAL_PASSAGE = "retrieval.passage"
TASK_RETRIEVAL_QUERY = "retrieval.query"
TASK_TEXT_MATCHING = "text-matching"

# ---------------------------------------------------------------------------
# Qdrant vector names and indexed fields
# ---------------------------------------------------------------------------

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"

INDEXED_FIELDS = {
    "source": PayloadSchemaType.KEYWORD,
    "chunk_id": PayloadSchemaType.KEYWORD,
    "file_path": PayloadSchemaType.KEYWORD,
    "folder_path": PayloadSchemaType.KEYWORD,
    "chunk_type": PayloadSchemaType.KEYWORD,
    "content_type": PayloadSchemaType.KEYWORD,
    "api_style": PayloadSchemaType.KEYWORD,
    "api_entities": PayloadSchemaType.KEYWORD,
    "global_sort_key": PayloadSchemaType.KEYWORD,
    "parent_chunk_id": PayloadSchemaType.KEYWORD,
}

# ---------------------------------------------------------------------------
# Retrieval tuning constants
# ---------------------------------------------------------------------------

RETRIEVAL_LIMIT = 50
RERANK_MIN_SCORE = -0.5
FUZZY_MIN_SCORE = 85
EXPANSION_SCORE = 0.0
EXPANSION_MEDIUM_CUTOFF = 10
EXPANSION_LOW_CUTOFF = 5
EXPANSION_MAX_TARGETS = 10

# ---------------------------------------------------------------------------
# Ingestion tuning constants
# ---------------------------------------------------------------------------

EMBED_BATCH_SIZE = 256
UPSERT_BATCH_SIZE = 256
PAGE_CONCURRENCY = 2
MAX_SECTION_CHARS = 3000
