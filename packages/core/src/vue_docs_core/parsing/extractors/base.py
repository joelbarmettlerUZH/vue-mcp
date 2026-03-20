"""Base protocol for entity extractors."""

import re
from pathlib import Path
from typing import Protocol

from vue_docs_core.models.entity import ApiEntity


class EntityExtractor(Protocol):
    """Protocol for source-specific entity extraction."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Scan documentation files to build an API entity dictionary.

        Returns a dict mapping entity name → ApiEntity.
        """
        ...

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return compiled regex patterns for matching import statements.

        Each pattern should have a capture group for the imported names.
        """
        ...
