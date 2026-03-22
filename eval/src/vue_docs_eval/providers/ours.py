"""Our MCP server provider - calls _do_search() directly with token instrumentation."""

import re
import time
from unittest.mock import patch

from vue_docs_eval.models import SearchResult
from vue_docs_server.startup import shutdown, startup
from vue_docs_server.tools.search import _do_search


class _InstrumentedContext:
    """Captures structured data from search pipeline info() messages."""

    def __init__(self):
        self.rerank_tokens: int | None = None
        self._messages: list[str] = []

    async def report_progress(self, *a, **kw):
        pass

    async def info(self, msg: str, *a, **kw):
        self._messages.append(msg)
        match = re.search(r"tokens:\s*(\d+)", msg)
        if match:
            self.rerank_tokens = int(match.group(1))

    async def warning(self, *a, **kw):
        pass

    async def error(self, *a, **kw):
        pass

    async def debug(self, *a, **kw):
        pass

    async def get_state(self, *a, **kw):
        return None

    async def set_state(self, *a, **kw):
        pass


class OursProvider:
    """Evaluates our own MCP server by calling _do_search() directly."""

    name = "ours"

    async def startup(self) -> None:
        startup()

    async def shutdown(self) -> None:
        shutdown()

    async def search(self, query: str, framework: str, max_results: int) -> SearchResult:
        ctx = _InstrumentedContext()
        embed_tokens: int | None = None

        # Patch JinaClient.embed to capture token count without modifying server code
        original_embed = None

        async def _capturing_embed(self_jina, texts, task=None, **kwargs):
            nonlocal embed_tokens
            result = await original_embed(self_jina, texts, task=task, **kwargs)
            embed_tokens = result.total_tokens
            return result

        from vue_docs_core.clients.jina import JinaClient

        original_embed = JinaClient.embed

        start = time.monotonic()
        with patch.object(JinaClient, "embed", _capturing_embed):
            text = await _do_search(query, source=framework, max_results=max_results, ctx=ctx)
        latency = time.monotonic() - start

        return SearchResult(
            text=text,
            latency_s=round(latency, 3),
            embed_tokens=embed_tokens,
            rerank_tokens=ctx.rerank_tokens,
        )
