"""Tests for the /health endpoint used by the status page."""

import json
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from vue_docs_server import health
from vue_docs_server.main import mcp
from vue_docs_server.startup import state


def _client() -> TestClient:
    return TestClient(mcp.http_app())


def _qdrant(status: str = "green", points: int = 42) -> MagicMock:
    qdrant = MagicMock()
    qdrant.collection_info.return_value = {"points_count": points, "status": status}
    return qdrant


def _patched_state(**overrides):
    values = {
        "db": MagicMock(),
        "qdrant": _qdrant(),
        "bm25": MagicMock(),
        "page_paths_by_source": {"vue": ["a.md", "b.md"], "pinia": ["c.md"]},
    }
    values.update(overrides)
    return patch.multiple(state, **values)


class TestHealthEndpoint:
    def test_ok_when_everything_is_up(self):
        loaded_at = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
        with _patched_state(), patch.object(health, "data_updated_at", return_value=loaded_at):
            response = _client().get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"] == {"data": "ok", "database": "ok", "qdrant": "ok"}
        assert body["sources"] == 2
        assert body["pages"] == 3
        assert body["points"] == 42
        assert body["version"]
        assert body["uptime_seconds"] >= 0
        assert body["data_updated"] == "2026-10-25T12:00:00+00:00"

    def test_degraded_when_database_is_down_without_leaking_details(self):
        db = MagicMock()
        db.ping.side_effect = RuntimeError("could not connect: password=hunter2 host=db")
        with _patched_state(db=db):
            response = _client().get("/health")

        assert response.status_code == 503
        assert response.json()["status"] == "degraded"
        assert response.json()["checks"]["database"] == "RuntimeError"
        assert "hunter2" not in response.text

    def test_degraded_when_qdrant_is_down(self):
        qdrant = MagicMock()
        qdrant.collection_info.side_effect = ConnectionError("refused")
        with _patched_state(qdrant=qdrant):
            response = _client().get("/health")

        assert response.status_code == 503
        assert response.json()["checks"]["qdrant"] == "ConnectionError"
        assert response.json()["points"] is None

    def test_degraded_when_collection_is_red(self):
        with _patched_state(qdrant=_qdrant(status="red")):
            response = _client().get("/health")

        assert response.status_code == 503
        assert response.json()["checks"]["qdrant"] == "collection red"

    def test_yellow_collection_is_still_healthy(self):
        """Yellow means Qdrant is optimising in the background; queries still work."""
        with _patched_state(qdrant=_qdrant(status="yellow")):
            response = _client().get("/health")

        assert response.status_code == 200

    def test_degraded_when_data_not_loaded(self):
        with _patched_state(bm25=None):
            response = _client().get("/health")

        assert response.status_code == 503
        assert response.json()["checks"]["data"] == "not loaded"

    def test_unavailable_dependencies_are_reported(self):
        with _patched_state(db=None, qdrant=None):
            response = _client().get("/health")

        assert response.status_code == 503
        assert response.json()["data_updated"] is None  # nothing has been loaded yet
        assert response.json()["checks"]["database"] == "unavailable"
        assert response.json()["checks"]["qdrant"] == "unavailable"

    @pytest.mark.asyncio
    async def test_slow_dependency_times_out_instead_of_hanging(self):
        """Timed on the handler itself: TestClient's loop teardown waits for worker threads."""
        db = MagicMock()
        db.ping.side_effect = lambda: time.sleep(0.5)
        with _patched_state(db=db), patch.object(health, "_CHECK_TIMEOUT", 0.05):
            started = time.monotonic()
            response = await health.health_check(MagicMock())

        assert time.monotonic() - started < 0.4
        assert response.status_code == 503
        assert json.loads(response.body)["checks"]["database"] == "TimeoutError"

    def test_only_get_is_allowed(self):
        with _patched_state():
            assert _client().post("/health").status_code == 405
