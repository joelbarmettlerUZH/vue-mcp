"""Context7 MCP server provider - connects via streamable-http transport."""

import logging
import os
import time

import httpx

from vue_docs_core.data.sources import SOURCE_REGISTRY
from vue_docs_eval.models import SearchResult

logger = logging.getLogger(__name__)

CONTEXT7_URL = "https://mcp.context7.com/mcp"

# Mapping from our framework names to Context7 library search terms
FRAMEWORK_TO_CONTEXT7: dict[str, str] = {
    "vue": "Vue.js",
    "vue-router": "Vue Router",
}


class Context7Provider:
    """Evaluates Context7's MCP server via their HTTP API."""

    name = "context7"

    def __init__(self):
        self._api_key: str = ""
        self._client: httpx.AsyncClient | None = None
        # Cache resolved library IDs to avoid redundant lookups
        self._library_ids: dict[str, str] = {}

    async def startup(self) -> None:
        self._api_key = os.environ.get("CONTEXT7_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("CONTEXT7_API_KEY environment variable not set")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _mcp_call(self, tool_name: str, arguments: dict) -> list[dict]:
        """Call a Context7 MCP tool via JSON-RPC over HTTP."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "CONTEXT7_API_KEY": self._api_key,
        }
        response = await self._client.post(CONTEXT7_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise RuntimeError(f"Context7 error: {data['error']}")

        # Extract text content from MCP result
        result = data.get("result", {})
        content = result.get("content", [])
        return content

    async def _resolve_library_id(self, framework: str) -> str:
        """Resolve a framework name to a Context7 library ID."""
        if framework in self._library_ids:
            return self._library_ids[framework]

        search_name = FRAMEWORK_TO_CONTEXT7.get(framework)
        if not search_name:
            source = SOURCE_REGISTRY.get(framework)
            search_name = source.display_name if source else framework

        content = await self._mcp_call(
            "resolve-library-id",
            {"libraryName": search_name, "query": search_name},
        )

        # Parse the text response to find the library ID
        for item in content:
            text = item.get("text", "")
            if text:
                # Context7 returns library IDs like "/vuejs/docs" in the text
                for line in text.split("\n"):
                    line = line.strip()
                    if line.startswith("/") and "/" in line[1:]:
                        self._library_ids[framework] = line.split()[0]
                        return self._library_ids[framework]

        raise RuntimeError(f"Could not resolve Context7 library ID for '{search_name}'")

    async def search(self, query: str, framework: str, max_results: int) -> SearchResult:
        library_id = await self._resolve_library_id(framework)

        start = time.monotonic()
        content = await self._mcp_call(
            "get-library-docs",
            {"libraryId": library_id, "query": query, "tokens": 5000},
        )
        latency = time.monotonic() - start

        # Concatenate all text content
        text_parts = [item.get("text", "") for item in content if item.get("text")]
        text = "\n".join(text_parts)

        return SearchResult(
            text=text,
            latency_s=round(latency, 3),
            embed_tokens=None,
            rerank_tokens=None,
        )
