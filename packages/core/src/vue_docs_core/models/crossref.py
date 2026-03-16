"""Cross-reference models."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class CrossRefType(str, Enum):
    HIGH = "high"  # guide <-> api
    MEDIUM = "medium"  # same-folder guide -> guide
    LOW = "low"  # cross-folder guide -> guide


class CrossReference(BaseModel):
    source_chunk_id: Annotated[
        str, Field(description="ID of the chunk containing the cross-reference")
    ]
    target_path: Annotated[
        str, Field(description="Resolved documentation-relative path of the reference target")
    ]
    link_text: Annotated[str, Field(description="Display text of the markdown link")]
    ref_type: Annotated[
        CrossRefType, Field(description="Priority classification of the cross-reference")
    ] = CrossRefType.LOW
