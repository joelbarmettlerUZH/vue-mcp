"""Hash store persistence for incremental updates."""

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileState:
    content_hash: str
    pipeline_version: str
    chunk_ids: list[str] = field(default_factory=list)
    last_indexed: str = ""


class IndexState:
    """Persistent hash store for tracking indexed file states."""

    def __init__(self, state_path: Path) -> None:
        self.path = state_path
        self._data: dict[str, dict] = {}
        if state_path.exists():
            self._data = json.loads(state_path.read_text(encoding="utf-8"))

    def get(self, file_path: str) -> FileState | None:
        entry = self._data.get(file_path)
        if entry is None:
            return None
        return FileState(**entry)

    def set(self, file_path: str, state: FileState) -> None:
        self._data[file_path] = dataclasses.asdict(state)

    def remove(self, file_path: str) -> None:
        self._data.pop(file_path, None)

    def all_file_paths(self) -> list[str]:
        return list(self._data.keys())

    def total_chunks(self) -> int:
        return sum(len(v.get("chunk_ids", [])) for v in self._data.values())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
