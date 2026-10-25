"""Health endpoint for status pages: checks loaded data, PostgreSQL and Qdrant.

Deliberately does not call Jina or Gemini: a status page polling a paid API would cost money.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from importlib.metadata import version

from starlette.requests import Request
from starlette.responses import JSONResponse

from vue_docs_server.startup import data_updated_at, state

logger = logging.getLogger(__name__)

_STARTED = time.monotonic()
_CHECK_TIMEOUT = 3.0


async def _run_check(name: str, check: Callable[[], object] | None) -> tuple[str, object]:
    """Run a blocking check in a thread; report failures by exception class only.

    This is a system boundary: a failing dependency must never turn into a 500, and
    exception messages can carry hostnames or credentials, so they only go to the log.
    """
    if check is None:
        return "unavailable", None
    try:
        return "ok", await asyncio.wait_for(asyncio.to_thread(check), _CHECK_TIMEOUT)
    except Exception as e:
        logger.warning("Health check %s failed", name, exc_info=True)
        return type(e).__name__, None


async def health_check(request: Request) -> JSONResponse:
    """Report 200 when the server can answer queries, 503 when a dependency is down."""
    db_status, _ = await _run_check("database", state.db.ping if state.db else None)
    qdrant_status, collection = await _run_check(
        "qdrant", state.qdrant.collection_info if state.qdrant else None
    )
    if qdrant_status == "ok" and collection["status"] == "red":
        qdrant_status = "collection red"

    checks = {
        "data": "ok" if state.is_ready else "not loaded",
        "database": db_status,
        "qdrant": qdrant_status,
    }
    healthy = all(v == "ok" for v in checks.values())

    updated = data_updated_at()
    body = {
        "status": "ok" if healthy else "degraded",
        "version": version("vue-docs-server"),
        "uptime_seconds": int(time.monotonic() - _STARTED),
        "checks": checks,
        "sources": len(state.page_paths_by_source),
        "pages": sum(len(paths) for paths in state.page_paths_by_source.values()),
        "points": collection["points_count"] if collection else None,
        "data_updated": updated.isoformat() if updated.year > 1 else None,
    }
    return JSONResponse(body, status_code=200 if healthy else 503)
