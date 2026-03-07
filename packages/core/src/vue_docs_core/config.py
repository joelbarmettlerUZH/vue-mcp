"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Jina AI
    jina_api_key: str = ""
    jina_embedding_model: str = "jina-embeddings-v4"
    jina_reranker_model: str = "jina-reranker-v3"

    # Gemini
    gemini_api_key: str = ""
    gemini_flash_lite_model: str = "gemini-2.5-flash-lite"
    gemini_flash_model: str = "gemini-2.5-flash"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "vue_docs"

    # Paths
    vue_docs_path: str = "./data/vue-docs/src"
    data_path: str = "./data"

    # Pipeline
    pipeline_version: str = "1"


settings = Settings()
