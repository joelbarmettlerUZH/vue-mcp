.PHONY: help install bootstrap lint lint-fix format-check format check test test-all test-integration ingest ingest-full ingest-status serve inspect all pr-ready docker-build docker-dev-up docker-dev-down docker-local-up docker-local-down docker-prod-up docker-prod-down docs docs-build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────

install: ## Install all workspace packages
	uv sync

bootstrap: ## Clone Vue docs + install dependencies
	bash scripts/bootstrap.sh

# ── Code Quality ───────────────────────────────────────────────────

lint: ## Run ruff linter (no changes)
	uv run ruff check .

lint-fix: ## Auto-fix lint issues
	uv run ruff check . --fix

format-check: ## Check formatting (no changes)
	uv run ruff format --check .

format: ## Apply formatting
	uv run ruff format .

check: lint format-check ## Lint + format check (CI-friendly, no modifications)

# ── Testing ────────────────────────────────────────────────────────

test: ## Run tests (skip integration tests requiring live APIs)
	uv run pytest -m "not integration"

test-all: ## Run all tests including integration tests (requires API keys)
	uv run pytest

test-integration: docker-dev-up ## Run integration tests against local infra
	uv run pytest -m integration -v

# ── Ingestion ──────────────────────────────────────────────────────

ingest: ## Run ingestion pipeline (incremental)
	uv run vue-docs-ingest run --verbose

ingest-full: ## Run ingestion pipeline (full re-index)
	uv run vue-docs-ingest run --verbose --full

ingest-status: ## Show ingestion status
	uv run vue-docs-ingest status

# ── Server ─────────────────────────────────────────────────────────

serve: ## Start the MCP server
	uv run vue-docs-server

# ── Debug ──────────────────────────────────────────────────────────

inspect: ## Inspect chunks for a file (usage: make inspect FILE=path/to/file.md)
	uv run python scripts/inspect_chunks.py $(FILE)

# ── Compound ───────────────────────────────────────────────────────

all: lint-fix format test ## Fix lint + format + test

pr-ready: lint-fix format test ## Verify everything passes before commit

# ── Docs ─────────────────────────────────────────────────────────

docs: ## Start docs dev server with hot reload
	cd docs && pnpm dev

docs-build: ## Build docs for production
	cd docs && pnpm build

# ── Docker ────────────────────────────────────────────────────────

docker-build: ## Build Docker images locally
	docker build --target server -t vue-mcp-server .
	docker build --target ingestion -t vue-mcp-ingestion .

docker-dev-up: ## Start dev infra (postgres + qdrant only)
	docker compose -f docker-compose.dev.yml up -d --wait

docker-dev-down: ## Stop dev infra
	docker compose -f docker-compose.dev.yml down

docker-local-up: ## Start full local stack with mkcert TLS
	docker compose -f docker-compose.local.yml up -d

docker-local-down: ## Stop full local stack
	docker compose -f docker-compose.local.yml down

docker-prod-up: ## Start production stack
	docker compose -f docker-compose.prod.yml up -d

docker-prod-down: ## Stop production stack
	docker compose -f docker-compose.prod.yml down
