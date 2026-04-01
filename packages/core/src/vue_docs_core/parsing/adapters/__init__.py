"""Pluggable source adapters for different documentation sources."""

from vue_docs_core.parsing.adapters.base import SourceAdapter
from vue_docs_core.parsing.adapters.nuxt import NuxtAdapter
from vue_docs_core.parsing.adapters.pinia import PiniaAdapter
from vue_docs_core.parsing.adapters.vite import ViteAdapter
from vue_docs_core.parsing.adapters.vitest import VitestAdapter
from vue_docs_core.parsing.adapters.vue import VueAdapter
from vue_docs_core.parsing.adapters.vue_devtools import VueDevToolsAdapter
from vue_docs_core.parsing.adapters.vue_router import VueRouterAdapter
from vue_docs_core.parsing.adapters.vueuse import VueUseAdapter

# Registry mapping source name -> adapter class
ADAPTER_REGISTRY: dict[str, type[SourceAdapter]] = {
    "vue": VueAdapter,
    "vue-router": VueRouterAdapter,
    "vueuse": VueUseAdapter,
    "vite": ViteAdapter,
    "vitest": VitestAdapter,
    "nuxt": NuxtAdapter,
    "pinia": PiniaAdapter,
    "vue-devtools": VueDevToolsAdapter,
}


def get_adapter(source_name: str) -> SourceAdapter:
    """Get the source adapter for a given source name.

    Raises ``KeyError`` if no adapter is registered for the source.
    """
    if source_name not in ADAPTER_REGISTRY:
        available = ", ".join(sorted(ADAPTER_REGISTRY.keys()))
        raise KeyError(f"No adapter registered for source '{source_name}'. Available: {available}")
    return ADAPTER_REGISTRY[source_name]()


__all__ = [
    "ADAPTER_REGISTRY",
    "NuxtAdapter",
    "PiniaAdapter",
    "SourceAdapter",
    "ViteAdapter",
    "VitestAdapter",
    "VueAdapter",
    "VueDevToolsAdapter",
    "VueRouterAdapter",
    "VueUseAdapter",
    "get_adapter",
]
