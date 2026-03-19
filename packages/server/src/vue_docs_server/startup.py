"""Load data from PostgreSQL (or JSON fallback), connect Qdrant on startup."""

import asyncio
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.postgres import PostgresClient
from vue_docs_core.clients.qdrant import QdrantDocClient
from vue_docs_core.config import settings
from vue_docs_core.models.entity import ApiEntity, EntityIndex
from vue_docs_core.retrieval.entity_matcher import EntityMatcher

logger = logging.getLogger(__name__)

_RELOAD_CHECK_INTERVAL = 60  # seconds


class ServerState:
    """Holds all runtime state loaded at startup."""

    def __init__(self):
        self.qdrant: QdrantDocClient | None = None
        self.bm25: BM25Model | None = None
        self.entity_index: EntityIndex = EntityIndex()
        self.synonym_table: dict[str, list[str]] = {}
        self.entity_matcher: EntityMatcher | None = None
        self.page_paths: list[str] = []
        self.folder_structure: dict[str, list[str]] = {}
        self.db: PostgresClient | None = None
        self.vue_docs_path: Path | None = None
        # Temporary directory for BM25 model extracted from PG
        self._bm25_tmp_dir: tempfile.TemporaryDirectory | None = None

    @property
    def is_ready(self) -> bool:
        return self.qdrant is not None and self.bm25 is not None


# Module-level singleton
state = ServerState()

# Track last reload timestamp for hot reload
_last_reload_ts: datetime = datetime.min.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# PostgreSQL data loading
# ---------------------------------------------------------------------------


def _load_from_pg(db: PostgresClient):
    """Load all server data from PostgreSQL."""
    state.entity_index = db.load_entities()
    state.synonym_table = db.load_synonyms()

    page_paths, folder_structure = db.load_pages_listing()
    state.page_paths = page_paths
    state.folder_structure = folder_structure

    # BM25: extract from PG blob to temp directory
    if state._bm25_tmp_dir:
        state._bm25_tmp_dir.cleanup()
    state._bm25_tmp_dir = tempfile.TemporaryDirectory(prefix="vue-mcp-bm25-")
    model = BM25Model()
    bm25_path = Path(state._bm25_tmp_dir.name) / "bm25_model"
    if db.load_bm25_model(bm25_path):
        model.load(bm25_path)
        logger.info("BM25 model loaded from PG (%d vocab tokens)", model.vocab_size)
    else:
        logger.warning("BM25 model not found in PG")
    state.bm25 = model

    # Entity matcher
    state.entity_matcher = EntityMatcher(
        entity_index=state.entity_index,
        synonym_table=state.synonym_table,
    )
    logger.info(
        "Entity matcher initialized with %d entities and %d synonyms",
        len(state.entity_index.entities),
        len(state.synonym_table),
    )


# ---------------------------------------------------------------------------
# JSON file loading (for local development without PG)
# ---------------------------------------------------------------------------


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
            entity_type=info.get("entity_type", "other"),
            page_path=info.get("page_path", ""),
            section=info.get("section", ""),
            related=info.get("related", []),
        )

    logger.info("Loaded %d API entities from files", len(entities))
    return EntityIndex(entities=entities)


def load_synonym_table(data_path: Path) -> dict[str, list[str]]:
    """Load the synonym/alias table from file or package data."""
    syn_path = data_path / "synonym_table.json"
    if syn_path.exists():
        with open(syn_path) as f:
            table = json.load(f)
        logger.info("Loaded %d synonym entries from files", len(table))
        return table

    from vue_docs_core.data import SYNONYM_TABLE

    logger.info("Loaded %d synonym entries from package data", len(SYNONYM_TABLE))
    return SYNONYM_TABLE


def _load_from_files(data_path: Path):
    """Load server data from JSON files (local dev fallback)."""
    state.entity_index = load_entity_dictionary(data_path)
    state.synonym_table = load_synonym_table(data_path)

    # Index state → page paths
    state_path = data_path / "state" / "index_state.json"
    if state_path.exists():
        with open(state_path) as f:
            raw_state = json.load(f)
        state.page_paths = sorted(raw_state.keys())
        state.folder_structure = {}
        for fp in state.page_paths:
            folder = fp.rsplit("/", 1)[0] if "/" in fp else ""
            state.folder_structure.setdefault(folder, []).append(fp)
        logger.info("Loaded %d page paths from files", len(state.page_paths))
    else:
        logger.warning("Index state not found at %s", state_path)

    # BM25 model
    model = BM25Model()
    model_path = data_path / "bm25_model"
    if model_path.exists():
        model.load(model_path)
        logger.info("BM25 model loaded from files (%d vocab tokens)", model.vocab_size)
    else:
        logger.warning("BM25 model not found at %s", model_path)
    state.bm25 = model

    # Entity matcher
    state.entity_matcher = EntityMatcher(
        entity_index=state.entity_index,
        synonym_table=state.synonym_table,
    )


# ---------------------------------------------------------------------------
# Startup / Shutdown / Hot Reload
# ---------------------------------------------------------------------------


def startup():
    """Initialize all server state."""
    global _last_reload_ts

    if settings.database_url:
        logger.info("Starting server, loading data from PostgreSQL")
        state.db = PostgresClient(settings.database_url)
        _load_from_pg(state.db)
        _last_reload_ts = state.db.get_max_updated_at()
    else:
        data_path = Path(settings.data_path)
        logger.info("Starting server, loading data from files at %s", data_path)
        _load_from_files(data_path)
        state.vue_docs_path = Path(settings.vue_docs_path).resolve()

    # Qdrant
    state.qdrant = QdrantDocClient()
    try:
        info = state.qdrant.collection_info()
        logger.info(
            "Qdrant connected: collection '%s' has %d points",
            state.qdrant.collection,
            info["points_count"],
        )
    except Exception as e:
        logger.warning(
            "Qdrant collection not available: %s. Server will start but search will fail "
            "until ingestion creates the collection.",
            e,
        )

    logger.info("Server startup complete")


def shutdown():
    """Clean up resources."""
    if state.qdrant:
        state.qdrant.close()
        state.qdrant = None
    if state.db:
        state.db.close()
        state.db = None
    if state._bm25_tmp_dir:
        state._bm25_tmp_dir.cleanup()
        state._bm25_tmp_dir = None
    state.entity_matcher = None
    logger.info("Server shutdown complete")


async def data_reload_loop():
    """Background task: poll PG for data changes and reload when detected."""
    global _last_reload_ts

    if not settings.database_url:
        logger.info("No DATABASE_URL configured, hot reload disabled")
        return

    while True:
        try:
            await asyncio.sleep(_RELOAD_CHECK_INTERVAL)
            max_updated = await asyncio.to_thread(state.db.get_max_updated_at)
            if max_updated > _last_reload_ts:
                logger.info(
                    "Data changed in PG (last: %s, new: %s), reloading...",
                    _last_reload_ts,
                    max_updated,
                )
                await asyncio.to_thread(_load_from_pg, state.db)
                _last_reload_ts = max_updated
                logger.info("Hot reload complete")
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in data reload loop")
