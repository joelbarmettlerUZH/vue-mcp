"""Index state persistence — PostgreSQL."""

from typing import Annotated

from pydantic import BaseModel, Field

from vue_docs_core.clients.postgres import PostgresClient


class FileState(BaseModel):
    content_hash: Annotated[str, Field(description="SHA-256 hash prefix of the file content")]
    pipeline_version: Annotated[
        str, Field(description="Pipeline version used when this file was last indexed")
    ]
    chunk_ids: Annotated[
        list[str],
        Field(description="List of chunk IDs originating from this file", default_factory=list),
    ]
    last_indexed: Annotated[
        str, Field(description="ISO timestamp of when this file was last indexed")
    ] = ""


class IndexState:
    """Persistent index state backed by PostgreSQL."""

    def __init__(self, db: PostgresClient, source: str = "vue"):
        self._db = db
        self._source = source

    def get(self, file_path: str) -> FileState | None:
        row = self._db.load_index_state_entry(file_path, source=self._source)
        if row is None:
            return None
        return FileState(
            content_hash=row["content_hash"],
            pipeline_version=row["pipeline_version"],
            chunk_ids=row["chunk_ids"],
            last_indexed=str(row["last_indexed"]) if row["last_indexed"] else "",
        )

    def set(self, file_path: str, state: FileState):
        self._db.save_index_state(
            file_path=file_path,
            content_hash=state.content_hash,
            pipeline_version=state.pipeline_version,
            chunk_ids=state.chunk_ids,
            last_indexed=state.last_indexed,
            source=self._source,
        )

    def remove(self, file_path: str):
        self._db.remove_index_state(file_path, source=self._source)

    def all_file_paths(self) -> list[str]:
        return self._db.all_index_file_paths(source=self._source)

    def total_chunks(self) -> int:
        return self._db.total_index_chunks(source=self._source)

    def save(self):
        """No-op — PG writes are immediate."""
