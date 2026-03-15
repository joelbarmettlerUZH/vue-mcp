"""File discovery, hash comparison, and change detection."""

import hashlib
from pathlib import Path


def find_markdown_files(docs_path: Path) -> list[Path]:
    """Return all .md files under docs_path, sorted alphabetically."""
    return sorted(docs_path.rglob("*.md"))


def hash_file(path: Path) -> str:
    """Return the SHA-256 hash of a file's raw bytes (first 16 hex chars)."""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]
