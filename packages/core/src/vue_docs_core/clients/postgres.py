"""PostgreSQL client using SQLAlchemy for shared data between ingestion and server."""

import gzip
import io
import logging
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    DateTime,
    LargeBinary,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from vue_docs_core.models.entity import ApiEntity, EntityIndex

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class PageRow(Base):
    __tablename__ = "pages"

    path: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EntityRow(Base):
    __tablename__ = "entities"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    page_path: Mapped[str] = mapped_column(String, nullable=False, default="")
    section: Mapped[str] = mapped_column(String, nullable=False, default="")
    related: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class SynonymRow(Base):
    __tablename__ = "synonyms"

    alias: Mapped[str] = mapped_column(String, primary_key=True)
    entity_names: Mapped[list] = mapped_column(JSONB, nullable=False)


class IndexStateRow(Base):
    __tablename__ = "index_state"

    file_path: Mapped[str] = mapped_column(String, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String, nullable=False)
    chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_indexed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelRow(Base):
    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PostgresClient:
    """Sync PostgreSQL client for reading/writing shared application data."""

    def __init__(self, database_url: str):
        self._engine = create_engine(database_url)
        self._session_factory = sessionmaker(self._engine)

    def create_tables(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self._engine)

    def close(self):
        self._engine.dispose()

    # ---- Read (used by server) -----------------------------------------------

    def load_entities(self) -> EntityIndex:
        """Load all API entities."""
        with self._session_factory() as session:
            rows = session.execute(select(EntityRow)).scalars().all()

        entities: dict[str, ApiEntity] = {}
        for row in rows:
            entities[row.name] = ApiEntity(
                name=row.name,
                entity_type=row.entity_type,
                page_path=row.page_path,
                section=row.section,
                related=row.related,
            )
        logger.info("Loaded %d entities from PG", len(entities))
        return EntityIndex(entities=entities)

    def load_synonyms(self) -> dict[str, list[str]]:
        """Load the synonym/alias table."""
        with self._session_factory() as session:
            rows = session.execute(select(SynonymRow)).scalars().all()

        table = {row.alias: row.entity_names for row in rows}
        logger.info("Loaded %d synonym entries from PG", len(table))
        return table

    def load_pages_listing(self) -> tuple[list[str], dict[str, list[str]]]:
        """Load page paths and folder structure from index_state table."""
        with self._session_factory() as session:
            rows = (
                session.execute(select(IndexStateRow.file_path).order_by(IndexStateRow.file_path))
                .scalars()
                .all()
            )

        folder_structure: dict[str, list[str]] = {}
        for fp in rows:
            folder = fp.rsplit("/", 1)[0] if "/" in fp else ""
            folder_structure.setdefault(folder, []).append(fp)

        logger.info(
            "Loaded %d page paths across %d folders from PG", len(rows), len(folder_structure)
        )
        return list(rows), folder_structure

    def load_bm25_model(self, target_dir: Path) -> bool:
        """Extract BM25 model blob into target directory. Returns True if found."""
        with self._session_factory() as session:
            row = session.execute(
                select(ModelRow).where(ModelRow.name == "bm25")
            ).scalar_one_or_none()

        if row is None:
            logger.warning("BM25 model not found in PG")
            return False

        target_dir.mkdir(parents=True, exist_ok=True)
        with (
            gzip.open(io.BytesIO(row.data), "rb") as gz,
            tarfile.open(fileobj=gz, mode="r:") as tar,
        ):
            tar.extractall(path=target_dir, filter="data")

        logger.info("Extracted BM25 model from PG to %s", target_dir)
        return True

    def read_page(self, path: str) -> str | None:
        """Read a single doc page by path."""
        with self._session_factory() as session:
            row = session.execute(
                select(PageRow.content).where(PageRow.path == path)
            ).scalar_one_or_none()
        return row

    def get_max_updated_at(self) -> datetime:
        """Get the most recent updated_at / last_indexed across all tracked tables."""
        with self._session_factory() as session:
            result = session.execute(
                select(
                    func.greatest(
                        select(func.max(PageRow.updated_at)).correlate(None).scalar_subquery(),
                        select(func.max(ModelRow.updated_at)).correlate(None).scalar_subquery(),
                        select(func.max(IndexStateRow.last_indexed))
                        .correlate(None)
                        .scalar_subquery(),
                    )
                )
            ).scalar()
        return result if result else datetime.min.replace(tzinfo=UTC)

    # ---- Write (used by ingestion) -------------------------------------------

    def save_entities(self, entities: dict[str, dict]):
        """Replace all API entities."""
        with self._session_factory() as session:
            session.execute(EntityRow.__table__.delete())
            for name, info in entities.items():
                session.add(
                    EntityRow(
                        name=name,
                        entity_type=info.get("entity_type", "other"),
                        page_path=info.get("page_path", ""),
                        section=info.get("section", ""),
                        related=info.get("related", []),
                    )
                )
            session.commit()
        logger.info("Saved %d entities to PG", len(entities))

    def save_synonyms(self, synonyms: dict[str, list[str]]):
        """Replace all synonyms."""
        with self._session_factory() as session:
            session.execute(SynonymRow.__table__.delete())
            for alias, names in synonyms.items():
                session.add(SynonymRow(alias=alias, entity_names=names))
            session.commit()
        logger.info("Saved %d synonyms to PG", len(synonyms))

    def save_pages(self, pages: dict[str, str]):
        """Upsert doc pages. pages = {path: markdown_content}."""
        with self._session_factory() as session:
            for path, content in pages.items():
                existing = session.get(PageRow, path)
                if existing:
                    existing.content = content
                else:
                    session.add(PageRow(path=path, content=content))
            session.commit()
        logger.info("Saved %d pages to PG", len(pages))

    def save_index_state(
        self,
        file_path: str,
        content_hash: str,
        pipeline_version: str,
        chunk_ids: list[str],
        last_indexed: str,
    ):
        """Upsert a single file's index state."""
        with self._session_factory() as session:
            existing = session.get(IndexStateRow, file_path)
            if existing:
                existing.content_hash = content_hash
                existing.pipeline_version = pipeline_version
                existing.chunk_ids = chunk_ids
                existing.last_indexed = last_indexed
            else:
                session.add(
                    IndexStateRow(
                        file_path=file_path,
                        content_hash=content_hash,
                        pipeline_version=pipeline_version,
                        chunk_ids=chunk_ids,
                        last_indexed=last_indexed,
                    )
                )
            session.commit()

    def remove_index_state(self, file_path: str):
        """Remove a file from the index state."""
        with self._session_factory() as session:
            row = session.get(IndexStateRow, file_path)
            if row:
                session.delete(row)
                session.commit()

    def load_index_state_entry(self, file_path: str) -> dict | None:
        """Load a single file's index state as a dict."""
        with self._session_factory() as session:
            row = session.get(IndexStateRow, file_path)
            if row is None:
                return None
            return {
                "content_hash": row.content_hash,
                "pipeline_version": row.pipeline_version,
                "chunk_ids": row.chunk_ids,
                "last_indexed": row.last_indexed,
            }

    def all_index_file_paths(self) -> list[str]:
        """Get all indexed file paths."""
        with self._session_factory() as session:
            return list(
                session.execute(select(IndexStateRow.file_path).order_by(IndexStateRow.file_path))
                .scalars()
                .all()
            )

    def total_index_chunks(self) -> int:
        """Get total chunk count across all indexed files."""
        with self._session_factory() as session:
            rows = session.execute(select(IndexStateRow.chunk_ids)).scalars().all()
        return sum(len(ids) for ids in rows)

    def save_bm25_model(self, model_dir: Path):
        """Tar + gzip the BM25 model directory and store as blob."""
        buf = io.BytesIO()
        with gzip.open(buf, "wb") as gz, tarfile.open(fileobj=gz, mode="w:") as tar:
            tar.add(model_dir, arcname=".")
        blob = buf.getvalue()

        with self._session_factory() as session:
            existing = session.get(ModelRow, "bm25")
            if existing:
                existing.data = blob
            else:
                session.add(ModelRow(name="bm25", data=blob))
            session.commit()
        logger.info("Saved BM25 model to PG (%d bytes compressed)", len(blob))
