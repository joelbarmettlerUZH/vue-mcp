"""Pluggable entity extractors for different documentation sources."""

from vue_docs_core.parsing.extractors.base import EntityExtractor
from vue_docs_core.parsing.extractors.generic import GenericEntityExtractor
from vue_docs_core.parsing.extractors.vite import ViteEntityExtractor
from vue_docs_core.parsing.extractors.vitest import VitestEntityExtractor
from vue_docs_core.parsing.extractors.vue import VueEntityExtractor
from vue_docs_core.parsing.extractors.vue_router import VueRouterEntityExtractor
from vue_docs_core.parsing.extractors.vueuse import VueUseEntityExtractor

# Registry mapping source name → extractor class
EXTRACTOR_REGISTRY: dict[str, type[EntityExtractor]] = {
    "vue": VueEntityExtractor,
    "vue-router": VueRouterEntityExtractor,
    "vueuse": VueUseEntityExtractor,
    "vite": ViteEntityExtractor,
    "vitest": VitestEntityExtractor,
}


def get_extractor(source_name: str) -> EntityExtractor:
    """Get the entity extractor for a source, falling back to generic."""
    cls = EXTRACTOR_REGISTRY.get(source_name, GenericEntityExtractor)
    return cls()


__all__ = [
    "EXTRACTOR_REGISTRY",
    "EntityExtractor",
    "GenericEntityExtractor",
    "ViteEntityExtractor",
    "VitestEntityExtractor",
    "VueEntityExtractor",
    "VueRouterEntityExtractor",
    "VueUseEntityExtractor",
    "get_extractor",
]
