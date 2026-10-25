# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Base: Python + uv + workspace source
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1

# The app runs from /app/.venv (uv). System pip is unused, and its vendored msgpack, urllib3 and
# pkg_resources copies are flagged by Trivy.
RUN python -m pip uninstall -y pip && rm -rf /usr/local/lib/python3.13/site-packages/pip*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

# Dependency cache layer: copy only manifests first
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/server/pyproject.toml packages/server/pyproject.toml
COPY packages/ingestion/pyproject.toml packages/ingestion/pyproject.toml

# Source code
COPY packages/ packages/

# ---------------------------------------------------------------------------
# Server image
# ---------------------------------------------------------------------------
FROM base AS server

RUN uv sync --frozen --no-dev --package vue-docs-server

ENV PATH="/app/.venv/bin:$PATH"

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "import httpx; httpx.get('http://localhost:8000/mcp', timeout=5)"]
CMD ["vue-docs-server"]

# ---------------------------------------------------------------------------
# Ingestion image
# ---------------------------------------------------------------------------
FROM base AS ingestion

# git links libcurl, which links libbrotli. `upgrade` pulls in security fixes (e.g. libbrotli1
# 1.1.0-2+deb13u1 for CVE-2026-111497) and changing this line invalidates the cached layer.
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    apt-get -y upgrade && \
    rm -rf /var/lib/apt/lists/*

RUN uv sync --frozen --no-dev --package vue-docs-ingestion

# Ingestion needs write access to /app/data (mounted volume)
RUN mkdir -p /app/data && chown app:app /app/data

ENV PATH="/app/.venv/bin:$PATH"

USER app
CMD ["vue-docs-ingest", "watch", "--verbose"]
