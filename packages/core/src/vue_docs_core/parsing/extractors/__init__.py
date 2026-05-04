"""Pluggable entity extractors for different documentation sources."""

from vue_docs_core.parsing.extractors.base import EntityExtractor
from vue_docs_core.parsing.extractors.formkit import FormKitEntityExtractor
from vue_docs_core.parsing.extractors.generic import GenericEntityExtractor
from vue_docs_core.parsing.extractors.nuxt import NuxtEntityExtractor
from vue_docs_core.parsing.extractors.pinia import PiniaEntityExtractor
from vue_docs_core.parsing.extractors.pinia_colada import PiniaColadaEntityExtractor
from vue_docs_core.parsing.extractors.shadcn_vue import ShadcnVueEntityExtractor
from vue_docs_core.parsing.extractors.vee_validate import VeeValidateEntityExtractor
from vue_docs_core.parsing.extractors.vite import ViteEntityExtractor
from vue_docs_core.parsing.extractors.vitepress import VitePressEntityExtractor
from vue_docs_core.parsing.extractors.vitest import VitestEntityExtractor
from vue_docs_core.parsing.extractors.vue import VueEntityExtractor
from vue_docs_core.parsing.extractors.vue_devtools import VueDevToolsEntityExtractor
from vue_docs_core.parsing.extractors.vue_router import VueRouterEntityExtractor
from vue_docs_core.parsing.extractors.vueuse import VueUseEntityExtractor

# Registry mapping source name → extractor class
EXTRACTOR_REGISTRY: dict[str, type[EntityExtractor]] = {
    "vue": VueEntityExtractor,
    "vue-router": VueRouterEntityExtractor,
    "vueuse": VueUseEntityExtractor,
    "vite": ViteEntityExtractor,
    "vitest": VitestEntityExtractor,
    "nuxt": NuxtEntityExtractor,
    "pinia": PiniaEntityExtractor,
    "vue-devtools": VueDevToolsEntityExtractor,
    "vitepress": VitePressEntityExtractor,
    "pinia-colada": PiniaColadaEntityExtractor,
    "vee-validate": VeeValidateEntityExtractor,
    "formkit": FormKitEntityExtractor,
    "shadcn-vue": ShadcnVueEntityExtractor,
}


def get_extractor(source_name: str) -> EntityExtractor:
    """Get the entity extractor for a source, falling back to generic."""
    cls = EXTRACTOR_REGISTRY.get(source_name, GenericEntityExtractor)
    return cls()


__all__ = [
    "EXTRACTOR_REGISTRY",
    "EntityExtractor",
    "FormKitEntityExtractor",
    "GenericEntityExtractor",
    "NuxtEntityExtractor",
    "PiniaColadaEntityExtractor",
    "PiniaEntityExtractor",
    "ShadcnVueEntityExtractor",
    "VeeValidateEntityExtractor",
    "ViteEntityExtractor",
    "VitePressEntityExtractor",
    "VitestEntityExtractor",
    "VueDevToolsEntityExtractor",
    "VueEntityExtractor",
    "VueRouterEntityExtractor",
    "VueUseEntityExtractor",
    "get_extractor",
]
