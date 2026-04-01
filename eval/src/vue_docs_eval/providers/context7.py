"""Context7 MCP server provider - connects via streamable-http transport."""

import logging
import os
import time

import httpx

from vue_docs_eval.models import SearchResult

logger = logging.getLogger(__name__)

CONTEXT7_URL = "https://mcp.context7.com/mcp"

# Pre-resolved Context7 library IDs (avoids extra API calls)
FRAMEWORK_TO_LIBRARY_ID: dict[str, str] = {
    "vue": "/vuejs/vue",
    "vue-router": "/vuejs/vue-router",
    "vueuse": "/vueuse/vueuse",
    "vite": "/vitejs/vite",
    "vitest": "/vitest-dev/vitest",
}


class Context7Provider:
    """Evaluates Context7's MCP server via their HTTP API."""

    name = "context7"

    def __init__(self):
        self._api_key: str = ""
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        self._api_key = os.environ.get("CONTEXT7_API_KEY", "")
        if not self._api_key:
            # Try loading from .env file
            from dotenv import dotenv_values

            env = dotenv_values(".env")
            self._api_key = env.get("CONTEXT7_API_KEY", "")
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

        result = data.get("result", {})
        content = result.get("content", [])
        return content

    async def search(self, query: str, framework: str, max_results: int) -> SearchResult:
        library_id = FRAMEWORK_TO_LIBRARY_ID.get(framework)
        if not library_id:
            raise ValueError(
                f"No Context7 library ID for framework '{framework}'. "
                f"Available: {list(FRAMEWORK_TO_LIBRARY_ID.keys())}"
            )

        start = time.monotonic()
        content = await self._mcp_call(
            "query-docs",
            {"libraryId": library_id, "query": query, "tokens": 5000},
        )
        latency = time.monotonic() - start

        text_parts = [item.get("text", "") for item in content if item.get("text")]
        text = "\n".join(text_parts)

        return SearchResult(
            text=text,
            latency_s=round(latency, 3),
        )
