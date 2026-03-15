"""Load entity dict, synonym table, BM25 model, connect Qdrant on startup."""

import json
import logging
from pathlib import Path

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.qdrant import QdrantDocClient
from vue_docs_core.config import settings
from vue_docs_core.models.entity import ApiEntity, EntityIndex

logger = logging.getLogger(__name__)


class ServerState:
    """Holds all runtime state loaded at startup."""

    def __init__(self) -> None:
        self.qdrant: QdrantDocClient | None = None
        self.bm25: BM25Model | None = None
        self.entity_index: EntityIndex = EntityIndex()
        self.synonym_table: dict[str, list[str]] = {}

    @property
    def is_ready(self) -> bool:
        return self.qdrant is not None and self.bm25 is not None


# Module-level singleton
state = ServerState()


def load_entity_dictionary(data_path: Path) -> EntityIndex:
    """Load the entity dictionary built by ingestion."""
    dict_path = data_path / "entity_dictionary.json"
    if not dict_path.exists():
        logger.warning("Entity dictionary not found at %s", dict_path)
        return EntityIndex()

    with open(dict_path) as f:
        raw = json.load(f)

    entities: dict[str, ApiEntity] = {}
    for name, info in raw.items():
        entities[name] = ApiEntity(
            name=name,
            page_path=info.get("page_path", ""),
            section=info.get("section", ""),
        )

    logger.info("Loaded %d API entities", len(entities))
    return EntityIndex(entities=entities)


def load_synonym_table(data_path: Path) -> dict[str, list[str]]:
    """Load the synonym/alias table."""
    syn_path = data_path / "synonym_table.json"
    if not syn_path.exists():
        logger.warning("Synonym table not found at %s", syn_path)
        return {}

    with open(syn_path) as f:
        table = json.load(f)

    logger.info("Loaded %d synonym entries", len(table))
    return table


def load_bm25_model(data_path: Path) -> BM25Model:
    """Load the fitted BM25 model."""
    model = BM25Model()
    model_path = data_path / "bm25_model"
    if model_path.exists():
        model.load(model_path)
        logger.info("BM25 model loaded (%d vocab tokens)", model.vocab_size)
    else:
        logger.warning("BM25 model not found at %s", model_path)
    return model


def startup() -> None:
    """Initialize all server state."""
    data_path = Path(settings.data_path)
    logger.info("Starting server, loading data from %s", data_path)

    state.entity_index = load_entity_dictionary(data_path)
    state.synonym_table = load_synonym_table(data_path)
    state.bm25 = load_bm25_model(data_path)
    state.qdrant = QdrantDocClient()

    # Verify Qdrant connection
    try:
        info = state.qdrant.collection_info()
        logger.info(
            "Qdrant connected: collection '%s' has %d points",
            state.qdrant.collection,
            info["points_count"],
        )
    except Exception as e:
        logger.error("Failed to connect to Qdrant: %s", e)
        raise

    logger.info("Server startup complete")


def shutdown() -> None:
    """Clean up resources."""
    if state.qdrant:
        state.qdrant.close()
        state.qdrant = None
    logger.info("Server shutdown complete")
