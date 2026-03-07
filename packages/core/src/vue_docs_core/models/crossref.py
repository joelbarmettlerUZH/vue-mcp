"""Cross-reference models."""

from enum import Enum

from pydantic import BaseModel


class CrossRefType(str, Enum):
    HIGH = "high"    # guide <-> api
    MEDIUM = "medium"  # same-folder guide -> guide
    LOW = "low"      # cross-folder guide -> guide


class CrossReference(BaseModel):
    source_chunk_id: str
    target_path: str
    link_text: str
    ref_type: CrossRefType = CrossRefType.LOW
