"""Usage analytics: log tool calls and resource reads to PostgreSQL."""

import logging

from vue_docs_server.startup import state

logger = logging.getLogger(__name__)


def _log(
    event_type: str,
    name: str,
    *,
    query: str | None = None,
    framework: str | None = None,
    latency_ms: int | None = None,
    response_chars: int | None = None,
    session_id: str | None = None,
    error: str | None = None,
) -> None:
    """Fire-and-forget usage log. Never raises."""
    if state.db:
        state.db.log_usage(
            event_type=event_type,
            name=name,
            query=query,
            framework=framework,
            latency_ms=latency_ms,
            response_chars=response_chars,
            session_id=session_id,
            error=error,
        )


def log_tool_call(
    tool_name: str,
    *,
    query: str | None = None,
    framework: str | None = None,
    latency_ms: int,
    response_chars: int,
    error: str | None = None,
) -> None:
    """Log a tool call."""
    _log(
        "tool_call",
        tool_name,
        query=query,
        framework=framework,
        latency_ms=latency_ms,
        response_chars=response_chars,
        error=error,
    )


def log_resource_read(
    resource_uri: str,
    *,
    framework: str | None = None,
    response_chars: int = 0,
) -> None:
    """Log a resource read."""
    _log(
        "resource_read",
        resource_uri,
        framework=framework,
        response_chars=response_chars,
    )
