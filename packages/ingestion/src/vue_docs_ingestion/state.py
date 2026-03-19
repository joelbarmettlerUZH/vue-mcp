"""Index state persistence — PostgreSQL primary, JSON file fallback."""

import json
from pathlib import Path
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
    """Persistent index state with PG or JSON file backend."""

    def __init__(self, state_path: Path | None = None, db: PostgresClient | None = None):
        self._db = db
        self._path = state_path
        self._data: dict[str, dict] = {}

        if db is None and state_path is not None and state_path.exists():
            self._data = json.loads(state_path.read_text(encoding="utf-8"))

    def get(self, file_path: str) -> FileState | None:
        if self._db:
            row = self._db.load_index_state_entry(file_path)
            if row is None:
                return None
            return FileState(
                content_hash=row["content_hash"],
                pipeline_version=row["pipeline_version"],
                chunk_ids=row["chunk_ids"],
                last_indexed=str(row["last_indexed"]) if row["last_indexed"] else "",
            )
        entry = self._data.get(file_path)
        if entry is None:
            return None
        return FileState(**entry)

    def set(self, file_path: str, state: FileState):
        if self._db:
            self._db.save_index_state(
                file_path=file_path,
                content_hash=state.content_hash,
                pipeline_version=state.pipeline_version,
                chunk_ids=state.chunk_ids,
                last_indexed=state.last_indexed,
            )
            return
        self._data[file_path] = state.model_dump()

    def remove(self, file_path: str):
        if self._db:
            self._db.remove_index_state(file_path)
            return
        self._data.pop(file_path, None)

    def all_file_paths(self) -> list[str]:
        if self._db:
            return self._db.all_index_file_paths()
        return list(self._data.keys())

    def total_chunks(self) -> int:
        if self._db:
            return self._db.total_index_chunks()
        return sum(len(v.get("chunk_ids", [])) for v in self._data.values())

    def save(self):
        """Persist state. No-op for PG backend (writes are immediate)."""
        if self._db:
            return
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
