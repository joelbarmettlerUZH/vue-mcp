"""Curated data shipped with the package."""

from vue_docs_core.data.sources import SOURCE_REGISTRY, VUE_SYNONYMS, SourceDefinition

# Backward-compatible alias: existing code imports SYNONYM_TABLE from here
SYNONYM_TABLE: dict[str, list[str]] = VUE_SYNONYMS

__all__ = [
    "SOURCE_REGISTRY",
    "SYNONYM_TABLE",
    "VUE_SYNONYMS",
    "SourceDefinition",
]
