"""Base protocol for source adapters.

A SourceAdapter bundles all source-specific customization hooks that the
shared ingestion pipeline calls at well-defined points.  Each documentation
source (Vue, Vue Router, Nuxt, ...) provides its own adapter implementation.
"""

import re
from pathlib import Path
from typing import Protocol

from vue_docs_core.models.entity import ApiEntity


class SourceAdapter(Protocol):
    """Protocol that every source adapter must satisfy."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def post_clone(self, repo_root: Path) -> None:
        """Run after ``git clone`` / ``git pull``.

        Use this to generate API docs (e.g. TypeDoc), install deps, or
        perform any other setup that must happen before file discovery.
        """
        ...

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Return the markdown files to ingest.

        Implementations handle i18n filtering, generated-file exclusion,
        and any other source-specific file selection logic.
        """
        ...

    # ------------------------------------------------------------------
    # Navigation / ordering
    # ------------------------------------------------------------------

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Parse the navigation/sidebar config into ``{page_path: sort_key}``.

        Sort keys have the format ``{section:02d}_{group:02d}_{item:02d}``.
        Files not returned here receive a ``99_`` fallback in the pipeline.
        """
        ...

    # ------------------------------------------------------------------
    # Content cleaning
    # ------------------------------------------------------------------

    def clean_content(self, raw: str) -> str:
        """Source-specific content cleaning applied *after* generic markdown
        stripping (blank-line collapsing, etc.).

        Examples: stripping ``<VueSchoolLink>``, ``<div class="options-api">``,
        ``[Try it in the Playground]`` links, ``<script setup>`` blocks.
        """
        ...

    # ------------------------------------------------------------------
    # Entity extraction (subsumes EntityExtractor)
    # ------------------------------------------------------------------

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Scan documentation files to build an API entity dictionary."""
        ...

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return compiled regex patterns for matching import statements."""
        ...

    # ------------------------------------------------------------------
    # Cross-reference classification
    # ------------------------------------------------------------------

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        """Folder pairs whose cross-links are classified as HIGH value.

        Example: ``[{"guide", "api"}]`` marks guide-to-api links as HIGH.
        """
        ...
