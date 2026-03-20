# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Base: Python + uv + workspace source
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1

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

RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

RUN uv sync --frozen --no-dev --package vue-docs-ingestion

# Ingestion needs write access to /app/data (mounted volume)
RUN mkdir -p /app/data && chown app:app /app/data

ENV PATH="/app/.venv/bin:$PATH"

USER app
CMD ["vue-docs-ingest", "watch", "--verbose"]
