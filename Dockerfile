# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Base: Python + uv + workspace source
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

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

EXPOSE 8000
CMD ["vue-docs-server"]

# ---------------------------------------------------------------------------
# Ingestion image
# ---------------------------------------------------------------------------
FROM base AS ingestion

RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

RUN uv sync --frozen --no-dev --package vue-docs-ingestion

ENV PATH="/app/.venv/bin:$PATH"

# Default: watch mode (scheduled ingestion)
CMD ["vue-docs-ingest", "watch", "--verbose"]
