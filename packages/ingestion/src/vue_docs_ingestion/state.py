"""Hash store persistence for incremental updates."""

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field


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
    """Persistent hash store for tracking indexed file states."""

    def __init__(self, state_path: Path):
        self.path = state_path
        self._data: dict[str, dict] = {}
        if state_path.exists():
            self._data = json.loads(state_path.read_text(encoding="utf-8"))

    def get(self, file_path: str) -> FileState | None:
        entry = self._data.get(file_path)
        if entry is None:
            return None
        return FileState(**entry)

    def set(self, file_path: str, state: FileState):
        self._data[file_path] = state.model_dump()

    def remove(self, file_path: str):
        self._data.pop(file_path, None)

    def all_file_paths(self) -> list[str]:
        return list(self._data.keys())

    def total_chunks(self) -> int:
        return sum(len(v.get("chunk_ids", [])) for v in self._data.values())

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
