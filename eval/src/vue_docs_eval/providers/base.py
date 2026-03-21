"""Provider protocol for evaluation search backends."""

from typing import Protocol, runtime_checkable

from vue_docs_eval.models import SearchResult


@runtime_checkable
class Provider(Protocol):
    """Interface that all search providers must implement."""

    name: str

    async def search(self, query: str, framework: str, max_results: int) -> SearchResult:
        """Run a search query and return the result with metadata."""
        ...

    async def startup(self) -> None:
        """Initialize the provider (e.g., connect to services)."""
        ...

    async def shutdown(self) -> None:
        """Clean up resources."""
        ...
