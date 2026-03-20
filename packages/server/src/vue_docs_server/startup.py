"""Load data from PostgreSQL, connect Qdrant on startup."""

import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.postgres import PostgresClient
from vue_docs_core.clients.qdrant import QdrantDocClient
from vue_docs_core.config import settings
from vue_docs_core.data.sources import SOURCE_REGISTRY, get_enabled_sources
from vue_docs_core.models.entity import ApiEntity, EntityIndex
from vue_docs_core.retrieval.entity_matcher import EntityMatcher

logger = logging.getLogger(__name__)

_HOT_RELOAD_INTERVAL = 3600  # seconds (1 hour)


class ServerState:
    """Holds all runtime state loaded at startup."""

    def __init__(self):
        self.qdrant: QdrantDocClient | None = None
        self.bm25: BM25Model | None = None

        # Per-source data
        self.entity_indices: dict[str, EntityIndex] = {}
        self.entity_matchers: dict[str, EntityMatcher] = {}
        self.page_paths_by_source: dict[str, list[str]] = {}
        self.folder_structures_by_source: dict[str, dict[str, list[str]]] = {}

        # Combined (merged from all sources, for ecosystem_search and backward compat)
        self.entity_index: EntityIndex = EntityIndex()
        self.synonym_table: dict[str, list[str]] = {}
        self.entity_matcher: EntityMatcher | None = None
        self.page_paths: list[str] = []
        self.folder_structure: dict[str, list[str]] = {}

        self.db: PostgresClient | None = None
        # Temporary directory for BM25 model extracted from PG
        self._bm25_tmp_dir: tempfile.TemporaryDirectory | None = None

    @property
    def is_ready(self) -> bool:
        return self.qdrant is not None and self.bm25 is not None


# Module-level singleton
state = ServerState()

# Track last reload timestamp for hot reload
_last_reload_ts: datetime = datetime.min.replace(tzinfo=UTC)


def _source_names() -> list[str]:
    """Return enabled source names."""
    sources = get_enabled_sources(settings.enabled_sources)
    return [s.name for s in sources]


# ---------------------------------------------------------------------------
# PostgreSQL data loading
# ---------------------------------------------------------------------------


def _load_from_pg(db: PostgresClient):
    """Load all server data from PostgreSQL."""
    source_names = _source_names()

    # Per-source entities and synonyms
    merged_entities: dict[str, ApiEntity] = {}
    merged_synonyms: dict[str, list[str]] = {}

    for sn in source_names:
        idx = db.load_entities(source=sn)
        state.entity_indices[sn] = idx
        merged_entities.update(idx.entities)

        syns = db.load_synonyms(source=sn)
        merged_synonyms.update(syns)

        page_paths, folder_structure = db.load_pages_listing(source=sn)
        state.page_paths_by_source[sn] = page_paths
        state.folder_structures_by_source[sn] = folder_structure

    # Also try loading without source filter to catch anything not source-specific
    all_entities = db.load_entities()
    merged_entities.update(all_entities.entities)

    state.entity_index = EntityIndex(entities=merged_entities)
    state.synonym_table = merged_synonyms

    # Merged page paths and folder structures
    all_page_paths: list[str] = []
    all_folder_structure: dict[str, list[str]] = {}
    for sn in source_names:
        all_page_paths.extend(state.page_paths_by_source.get(sn, []))
        for folder, pages in state.folder_structures_by_source.get(sn, {}).items():
            all_folder_structure.setdefault(folder, []).extend(pages)
    state.page_paths = sorted(set(all_page_paths))
    state.folder_structure = all_folder_structure

    # BM25: extract from PG blob to temp directory
    if state._bm25_tmp_dir:
        state._bm25_tmp_dir.cleanup()
    state._bm25_tmp_dir = tempfile.TemporaryDirectory(prefix="vue-mcp-bm25-")
    model = BM25Model()
    bm25_path = Path(state._bm25_tmp_dir.name) / "bm25_model"
    if not db.load_bm25_model(bm25_path):
        raise RuntimeError("BM25 model not found in PG. Run ingestion first.")
    model.load(bm25_path)
    logger.info("BM25 model loaded from PG (%d vocab tokens)", model.vocab_size)
    state.bm25 = model

    # Per-source entity matchers
    for sn in source_names:
        source_def = SOURCE_REGISTRY.get(sn)
        source_syns = source_def.synonyms if source_def else {}
        state.entity_matchers[sn] = EntityMatcher(
            entity_index=state.entity_indices.get(sn, EntityIndex()),
            synonym_table=source_syns,
        )

    # Combined entity matcher
    state.entity_matcher = EntityMatcher(
        entity_index=state.entity_index,
        synonym_table=state.synonym_table,
    )
    logger.info(
        "Entity matchers initialized: %d per-source + combined (%d entities, %d synonyms)",
        len(state.entity_matchers),
        len(state.entity_index.entities),
        len(state.synonym_table),
    )


# ---------------------------------------------------------------------------
# Startup / Shutdown / Hot Reload
# ---------------------------------------------------------------------------


def startup():
    """Initialize all server state."""
    global _last_reload_ts

    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Set it in .env or as an environment variable."
        )

    logger.info("Starting server, loading data from PostgreSQL")
    state.db = PostgresClient(settings.database_url)
    _load_from_pg(state.db)
    _last_reload_ts = state.db.get_max_updated_at()

    # Qdrant
    state.qdrant = QdrantDocClient()
    info = state.qdrant.collection_info()
    logger.info(
        "Qdrant connected: collection '%s' has %d points",
        state.qdrant.collection,
        info["points_count"],
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


async def hot_reload_loop(register_resources_fn):
    """Background task: reload data from PG and refresh concrete resources hourly."""
    global _last_reload_ts

    while True:
        try:
            await asyncio.sleep(_HOT_RELOAD_INTERVAL)
            max_updated = await asyncio.to_thread(state.db.get_max_updated_at)
            if max_updated > _last_reload_ts:
                logger.info(
                    "Data changed in PG (last: %s, new: %s), reloading...",
                    _last_reload_ts,
                    max_updated,
                )
                await asyncio.to_thread(_load_from_pg, state.db)
                _last_reload_ts = max_updated
                await asyncio.to_thread(register_resources_fn)
                logger.info("Hot reload complete (data + resources)")
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in hot reload loop")
