"""Pluggable source adapters for different documentation sources."""

from vue_docs_core.parsing.adapters.base import SourceAdapter
from vue_docs_core.parsing.adapters.vue import VueAdapter
from vue_docs_core.parsing.adapters.vue_router import VueRouterAdapter

# Registry mapping source name -> adapter class
ADAPTER_REGISTRY: dict[str, type[SourceAdapter]] = {
    "vue": VueAdapter,
    "vue-router": VueRouterAdapter,
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
    "SourceAdapter",
    "VueAdapter",
    "VueRouterAdapter",
    "get_adapter",
]
