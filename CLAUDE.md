# Vue Documentation MCP Server

MCP server providing semantic search and retrieval over Vue.js documentation. Combines dense embeddings (Jina) and sparse
search (BM25) to return structure-aware, readable documentation fragments.

## Repository Structure

```
packages/
  core/       Shared library: models, clients (Jina, Qdrant, Gemini, BM25, PostgreSQL), parsing, retrieval
  ingestion/  CLI tool (Typer): scan → parse → enrich → embed → store
  server/     MCP server (FastMCP): tools, resources, prompts, query pipeline
eval/         Evaluation suite (separate package, not shipped)
tests/        Root-level pytest suite
scripts/      Deployment, backup, restore, and debug utilities
```

All packages use `hatchling` build backend, Python ≥3.13, and share `vue-docs-core` via `[tool.uv.sources]` workspace
references.

## Commands

All commands are available via `make`. Run `make help` to see the full list.

| Command | What it does |
|---|---|
| `make install` | Install all workspace packages (`uv sync`) |
| `make bootstrap` | Clone Vue docs + install dependencies |
| `make lint` | Run ruff linter (no changes) |
| `make lint-fix` | Auto-fix lint issues |
| `make format` | Apply formatting |
| `make check` | Lint + format check (CI-friendly, no modifications) |
| `make test` | Run tests (skips integration tests requiring live APIs) |
| `make test-all` | Run all tests including integration tests |
| `make ingest` | Run ingestion pipeline (incremental) |
| `make ingest-full` | Run ingestion pipeline (full re-index) |
| `make serve` | Start the MCP server |
| `make inspect FILE=<path>` | Debug chunk output for a markdown file |
| `make pr-ready` | Fix lint + format + test (run before committing) |
| `make docker-build` | Build both Docker images locally |
| `make docker-up` | Start all services via Docker Compose |
| `make docker-down` | Stop all services |

For single-file test runs: `uv run pytest tests/test_server.py -v`

## Verification

Before committing, always run:

```bash
make pr-ready
```

## Deployment

The server is deployed as a Docker Compose stack on an Infomaniak OpenStack VM.

### Architecture

```
Internet → Traefik (:80/:443, TLS via Let's Encrypt) → MCP Server (:8000, streamable-http)
                                                             ├── PostgreSQL (shared data layer)
                                                             ├── Qdrant (vector search)
                                                             └── Ingestion (self-scheduling, writes to PG + Qdrant)
```

### Services

| Service | Image | Purpose |
|---|---|---|
| `mcp-server` | `ghcr.io/.../vue-mcp-server` | FastMCP server (streamable-http transport) |
| `ingestion` | `ghcr.io/.../vue-mcp-ingestion` | Self-scheduling pipeline (`watch` command, runs every 24h) |
| `postgres` | `postgres:17-alpine` | Shared data: entities, synonyms, pages, BM25 model, index state |
| `qdrant` | `qdrant/qdrant:v1.17.0` | Vector database (dense + sparse hybrid search) |
| `traefik` | `traefik:v3.6` | Reverse proxy, TLS, rate limiting (60 req/min, 10 concurrent, 100KB body) |

### Docker Images

One multi-target `Dockerfile` produces two images:
- **server**: `vue-docs-core` + `fastmcp` + `psycopg` + `sqlalchemy`. No git.
- **ingestion**: `vue-docs-core` + `typer` + `rich` + `psycopg` + `sqlalchemy` + `git`.

Build locally: `make docker-build`

### Data Flow

PostgreSQL is the shared data layer between ingestion (writes) and server (reads). No shared filesystem volumes for
application data. The `data/` directory is gitignored and only used for local development without PG.

### Local Development with Docker

Uses `docker-compose.override.yml` (gitignored) for mkcert TLS via nip.io:

```bash
mkcert -install
mkcert -cert-file certs/local.pem -key-file certs/local-key.pem "$(hostname -I | awk '{print $1}').nip.io"
DOMAIN=$(hostname -I | awk '{print $1}').nip.io docker compose up -d
```

### Production Deployment

```bash
# On the VM: /opt/vue-mcp/.env.production (from .env.production.example)
# Set TLS_CERTRESOLVER=letsencrypt, ACME_EMAIL, DOMAIN, API keys
docker compose up -d
```

### Server Transport

The server supports two transport modes via `SERVER_TRANSPORT` env var:
- `stdio` (default): for local MCP client connections
- `streamable-http`: for production, serves on `SERVER_HOST:SERVER_PORT/mcp`

### Hot Reload

The server polls PostgreSQL every 60 seconds for data changes. When ingestion writes new entities, pages, or BM25
models, the server reloads them automatically with zero downtime.

### Backup & Restore

```bash
scripts/backup.sh [backup_dir]    # pg_dump + Qdrant snapshot, 7-day rotation
scripts/restore.sh <dump.sql.gz> [snapshot]  # Restore from backup
```

### CI/CD

- `.github/workflows/ci.yml`: Lint + test on PRs
- `.github/workflows/build-and-push.yml`: Build both images, push to GHCR on push to main
- `scripts/deploy.sh`: SSH to VM, pull images, restart stack

## Design Principles

- **Structure-aware chunking.** Respect the documentation's heading hierarchy (page → section → subsection → block).
  Never use fixed-size token chunking.
- **Readable reconstruction.** Reassemble results into coherent mini-documents using metadata and sort keys, returned in
  documentation reading order, preserving the natural flow of the docs.
- **Deterministic where possible.** Entity extraction, cross-references, and markdown parsing use deterministic methods.
  Reserve LLM calls for enrichment and summarization at indexing time.
- **Hybrid retrieval.** Every search combines dense semantic embeddings, BM25 sparse search, and entity metadata
  boosting. No single retrieval method is trusted alone.
- **Unified embedding space.** All content types (prose, code, images, summaries, HyPE questions) share one embedding
  model (jina-embeddings-v4). No separate code or image embedding models.
- **Cost-conscious.** Per-query API cost must stay under $0.001. Favor token-based pricing, cheap LLMs for query-time
  tasks, and deterministic processing wherever possible.
- **Incremental by design.** Content hashing at every layer to skip unchanged files during re-indexing.

## Coding Conventions

1. **Pydantic models for all data structures.** Use `BaseModel` with `Annotated[type, Field(description="...")]` for
   rich metadata. Use `str` mixin on Enums for Qdrant payload compatibility (`class ChunkType(str, Enum)`).

2. **Async-first.** All I/O operations (Jina, Qdrant, Gemini, file reads) use `async`/`await`. Use `asyncio.gather()`
   for parallel operations.

3. **Type-hint everything.** Return types mandatory. Use modern syntax: `str | None` not `Optional[str]`, `list[str]`
   not `List[str]`. Use `Annotated` for Pydantic field metadata.

4. **Fail fast.** No defensive try-catch wrappers. Let exceptions propagate unless you're at a system boundary (API
   calls, user input).

5. **No heavy frameworks.** No LangChain, LlamaIndex, sentence-transformers, or torch. Jina and Gemini are HTTP
   requests. RRF fusion is ~20 lines. Keep the dependency tree shallow.

6. **Import conventions:**
   - Within a package: import from specific modules (`from vue_docs_core.models.chunk import Chunk`)
   - Across packages: import from `__init__.py` re-exports (`from vue_docs_core.models import Chunk`)
   - `models/__init__.py` re-exports the public interface for clean external imports

7. **Configuration via Settings singleton.** `vue_docs_core.config.Settings` loads from `.env` via Pydantic Settings.
   Constants live alongside Settings in `config.py`. Reference with `from vue_docs_core.config import settings`.

8. **Server state via singleton.** `vue_docs_server.startup.ServerState` holds loaded resources (entity dict, BM25
   model, Qdrant client, PG client). Initialized at server startup, accessed by tools. Supports hot reload from PG.

9. **SQLAlchemy ORM for PostgreSQL.** ORM models in `vue_docs_core.clients.postgres`. Sync `psycopg` driver. Tables
   created via `Base.metadata.create_all()`. No separate migration tool or SQL scripts.

10. **Curated data as package code.** Static lookup tables (e.g., synonym table) live as Python dicts in
    `vue_docs_core.data`, not as external files.

## Testing

- **Framework:** pytest + pytest-asyncio, `asyncio_mode = "auto"`
- **Location:** `tests/` at repo root
- **Integration tests:** Marked with `@pytest.mark.integration`, skipped by default (require live API keys)
- **Mocking pattern:** Use `unittest.mock.AsyncMock` for FastMCP Context and async clients. Use `patch()` on client
  methods. Helper functions (`_mock_ctx()`, `_make_hit()`) over pytest fixtures for test data construction.
- **Test before commit:** `make test` must pass (or `make pr-ready` for the full check)

## Key Technical Decisions

| Decision | Rationale |
|---|---|
| Jina AI as unified search provider | Single vendor, single token pool, single embedding space |
| No LLM at query time | Per-query LLM cost + hallucination risk; vocab gap handled by HyPE at indexing time |
| `bm25s` for sparse vectors | Lightweight, no external API needed |
| `markdown-it-py` for parsing | Token/tree API, heading hierarchy, code blocks, links, images |
| `rapidfuzz` for entity matching | Sub-millisecond fuzzy matching with typo tolerance |
| FastMCP with middleware | Error handling, timing, response limiting as composable layers |
| PostgreSQL as shared data layer | Decouples ingestion and server containers, atomic writes, simple backup (`pg_dump`) |
| SQLAlchemy ORM | Typed models, `create_tables()` for schema management, no raw SQL |
| Two Docker images from one Dockerfile | Shared base layer, separate concerns (server vs ingestion), independent restart |
| Traefik for reverse proxy | Auto TLS via Let's Encrypt, Docker-native service discovery, built-in rate limiting |
| Self-scheduling ingestion | `watch` command with configurable interval, no host cron jobs needed |
| Server hot reload | Background task polls PG every 60s, zero-downtime data refresh |

## External Services

| Service | Purpose | Client |
|---|---|---|
| Jina AI | Embeddings (jina-embeddings-v4) + reranking (jina-reranker-v3) | `httpx` |
| Google Gemini | Contextual enrichment, HyPE generation, RAPTOR summaries (ingestion only) | `google-genai` |
| Qdrant | Vector database (dense + sparse hybrid search) | `qdrant-client` |
| PostgreSQL | Shared data layer (entities, synonyms, pages, index state, BM25 model) | `sqlalchemy` + `psycopg` |

API keys configured via `.env` (see `.env.example`). All API calls go through clients in
`packages/core/src/vue_docs_core/clients/`.

## Ruff Configuration

Ruff handles both linting and formatting. Config lives in root `pyproject.toml`:
- Line length: 100
- Target: Python 3.13
- Rules: E, W, F, I, UP, B, SIM, TCH, RUF
- Quote style: double
- isort knows: `vue_docs_core`, `vue_docs_ingestion`, `vue_docs_server`

Don't manually enforce style rules. Run `make lint-fix && make format` instead.

## Data Flow

**Ingestion** (offline, self-scheduled): Clone/pull Vue docs → parse into structural chunks → extract entities +
cross-refs → enrich with contextual prefixes (Gemini) → generate HyPE questions (Gemini) → embed all (Jina) → generate
BM25 sparse vectors → upsert to Qdrant → save entities, synonyms, pages, BM25 model, and index state to PostgreSQL.

**Query** (online, per-request): Embed query (Jina) + BM25 sparse vector → hybrid search (Qdrant: dense + BM25, native
RRF) → resolve HyPE hits → cross-reference expansion → reranking (Jina) → reconstruction (sort by reading order, merge
adjacent, format). No LLM calls at query time.

## Do Not

- Add LangChain, LlamaIndex, or similar orchestration frameworks. Use direct HTTP clients instead.
- Use fixed-size token chunking. Chunk at structural boundaries (headings).
- Store HyPE embeddings as additional vectors on existing points. Store them as separate Qdrant points with
  `parent_chunk_id`.
- Edit `uv.lock` manually. Use `uv add/remove` for dependency changes.
- Commit `.env`, `.env.production`, or API keys. Use `.env.example` as the template.
- Return empty results from search tools. Always fall back to broader scope or RAPTOR summary nodes.
- Write raw SQL. Use SQLAlchemy ORM models in `vue_docs_core.clients.postgres`.
- Store generated data as files. All ingestion output goes to PostgreSQL and Qdrant.
- Add `init-db.sql` or migration scripts. SQLAlchemy `create_tables()` is the source of truth for schema.
