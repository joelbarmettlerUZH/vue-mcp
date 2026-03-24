# Vue Ecosystem MCP Server

MCP server providing semantic search and retrieval over Vue ecosystem documentation. Supports multiple frameworks
(Vue.js, Vue Router, and more planned). Combines dense embeddings (Jina) and sparse search (BM25) to return
structure-aware, readable documentation fragments.

## Repository Structure

```
packages/
  core/       Shared library: models, clients (Jina, Qdrant, Gemini, BM25, PostgreSQL), parsing, adapters
  ingestion/  CLI tool (Typer): scan → parse → enrich → embed → store
  server/     MCP server (FastMCP): tools, resources, prompts, query pipeline
eval/         Evaluation suite: multi-provider comparison (ours vs Context7), LLM judge, metrics
tests/        Root-level pytest suite
scripts/      Deployment, backup, restore, and debug utilities
docs/         Documentation site (VitePress), deployed to vue-mcp.org
```

All packages use `hatchling` build backend, Python >=3.13, and share `vue-docs-core` via `[tool.uv.sources]` workspace
references.

## Commands

All commands are available via `make`. Run `make help` to see the full list.

| Command | What it does |
|---|---|
| `make install` | Install all workspace packages (`uv sync`) |
| `make bootstrap` | Clone Vue + Vue Router docs + install dependencies |
| `make lint` | Run ruff linter (no changes) |
| `make lint-fix` | Auto-fix lint issues |
| `make format` | Apply formatting |
| `make check` | Lint + format check (CI-friendly, no modifications) |
| `make test` | Run tests (skips integration tests requiring live APIs) |
| `make test-all` | Run all tests including integration tests |
| `make ingest` | Run ingestion pipeline (incremental, all enabled sources) |
| `make ingest-full` | Run ingestion pipeline (full re-index) |
| `make serve` | Start the MCP server |
| `make inspect FILE=<path>` | Debug chunk output for a markdown file |
| `make pr-ready` | Fix lint + format + test (run before committing) |
| `make deploy` | Deploy latest images to production (syncs compose file, pulls from GHCR, restarts) |
| `make docker-build` | Build both Docker images locally |
| `make docker-dev-up` | Start dev infra (postgres + qdrant only) |
| `make docker-dev-down` | Stop dev infra |
| `make docker-local-up` | Start full local stack with mkcert TLS |
| `make docker-local-down` | Stop full local stack |
| `make docker-prod-up` | Start production stack |
| `make docker-prod-down` | Stop production stack |
| `make test-integration` | Start dev infra + run integration tests |
| `make eval` | Run eval against our server |
| `make eval-compare` | Run eval comparing ours vs Context7 |
| `make eval-generate FRAMEWORK=vue DOCS=path` | Generate evaluation questions |

For single-file test runs: `uv run pytest tests/test_server.py -v`

## Verification

Before committing, always run:

```bash
make pr-ready
```

## Multi-Framework Architecture

The ingestion pipeline uses a **SourceAdapter** pattern to support multiple documentation sources. Each framework
implements its own adapter with source-specific hooks, while sharing the common pipeline backbone.

### SourceAdapter Protocol

Each adapter (in `packages/core/src/vue_docs_core/parsing/adapters/`) implements:

| Hook | Purpose |
|---|---|
| `post_clone(repo_root)` | Run after git clone (e.g. TypeDoc generation for Vue Router) |
| `discover_files(docs_path)` | File discovery with filtering (e.g. exclude `zh/` translations) |
| `parse_sort_keys(repo_root)` | Parse sidebar/navigation config into sort key map |
| `clean_content(raw)` | Source-specific content cleaning (e.g. strip `<VueSchoolLink>`, API-style divs) |
| `build_entity_dictionary(docs_path)` | Build API entity dictionary from docs |
| `get_import_patterns()` | Regex patterns for matching import statements in code blocks |
| `high_value_folder_pairs` | Folder pairs for HIGH-value cross-reference classification |

### Registered Adapters

| Source | Adapter | Key Behaviors |
|---|---|---|
| `vue` | `VueAdapter` | Strips `<div class="options-api">` wrappers, Playground links. Single `config.ts` sidebar. |
| `vue-router` | `VueRouterAdapter` | Strips `<VueSchoolLink>`, `<RuleKitLink>`, `<script setup>` blocks. Excludes `zh/`. Split sidebar config (`config/en.ts`). Optional TypeDoc API generation (graceful skip if no npm). |

### Adding a New Framework

Follow these steps end-to-end. Use the Vue Router adapter (`vue_router.py`) as a reference implementation.

#### 1. Analyze the documentation source

Clone the repo and study its structure before writing any code:

- What is the docs subpath within the repo? (e.g. `src/`, `packages/docs/`, `docs/`)
- What doc framework is used? (VitePress, Nuxt Content, custom)
- Where is the sidebar/navigation config?
- Are there i18n directories to exclude?
- Are there auto-generated files (TypeDoc, etc.) that need a build step?
- What custom components or syntax need stripping?
- What are the API entities and how are they organized?

#### 2. Create the adapter

Create `packages/core/src/vue_docs_core/parsing/adapters/{name}.py` implementing:

- `post_clone()`: any post-clone setup (npm build for TypeDoc, etc.). Must gracefully skip if tools are unavailable
  (e.g. no npm in Docker). Use `shutil.which()` to check.
- `discover_files()`: return sorted list of `.md` files, excluding translations, generated dirs, etc.
- `parse_sort_keys()`: parse the sidebar config into `{page_path: sort_key}` map. Different doc frameworks need
  different parsers (VitePress `config.ts`, Nuxt Content `.navigation.yml`, etc.).
- `clean_content()`: strip framework-specific noise (custom Vue components, rendering directives, sponsor blocks,
  standalone `<script setup>` blocks). Be careful not to strip content inside code fences.
- `build_entity_dictionary()`: scan API docs for entity names. Seed with known APIs if the docs structure is unusual.
- `get_import_patterns()`: regex patterns matching `import { X } from "{package}"`.
- `high_value_folder_pairs`: which top-level folder pairs produce HIGH-value cross-references.

Register the adapter in `adapters/__init__.py` ADAPTER_REGISTRY.

#### 3. Create the entity extractor (optional)

If the framework's API docs follow a non-standard structure, create a dedicated extractor in
`packages/core/src/vue_docs_core/parsing/extractors/{name}.py`. Register it in `extractors/__init__.py`
EXTRACTOR_REGISTRY. Otherwise the adapter's `build_entity_dictionary()` can use the generic extractor or a hardcoded
seed list.

#### 4. Add source definition and synonyms

In `packages/core/src/vue_docs_core/data/sources.py`:

- Add a synonym dict (`{NAME}_SYNONYMS`) mapping developer phrases to API entity names.
- Add a `SourceDefinition` entry to `SOURCE_REGISTRY` with: `name`, `display_name`, `git_url`, `docs_subpath`,
  `base_url`, `import_packages`, `synonyms`, `gemini_context`.

#### 5. Run the ingestion locally

```bash
# Start dev infra
make docker-dev-up

# Clone the docs and run ingestion
ENABLED_SOURCES=vue,vue-router,{name} uv run vue-docs-ingest run --source {name} --verbose

# Verify with dry run first if unsure
uv run vue-docs-ingest run --source {name} --dry-run
```

Check the output for: file count, chunk count, noise in content, entity references, cross-references, small/large
chunk warnings. Fix adapter issues and re-run until clean.

#### 6. Run evaluation

```bash
# Generate eval questions
make eval-generate FRAMEWORK={name} DOCS=data/{name}-docs/{subpath}

# Run eval (ours only, quick check)
uv run vue-docs-eval run --providers ours --frameworks {name}

# Run comparison against Context7
uv run vue-docs-eval run --providers ours,context7 --frameworks {name}
```

Target: composite score >= 4.5/5, API recall >= 85%.

#### 7. Update documentation

- Add framework page: `docs/frameworks/{name}.md` with tools, resources, prompts, and benchmark results
- Update `docs/frameworks/index.md`: add to the Available table, move from Planned to Available in roadmap
- Update `docs/.vitepress/config.ts`: add to sidebar Frameworks section
- Update `docs/guide/what-is-vue-mcp.md`: update the supported frameworks table
- Update `docs/index.md` if headline stats change (question count, etc.)
- Update `README.md` supported frameworks table

#### 8. Update scripts

- `scripts/bootstrap.sh`: add git clone for the new docs repo

#### 9. Run tests and lint

```bash
make pr-ready   # lint + format + test
```

#### 10. Deploy

```bash
# Add ENABLED_SOURCES to .env.production on the server (via SSH)
# Then:
git push                    # triggers GHCR image build
gh run watch $(gh run list --workflow=build-and-push.yml -L 1 --json databaseId -q '.[0].databaseId')
make deploy                 # syncs compose file, pulls images, restarts
```

The ingestion container will clone the new docs and run the pipeline on its next cycle. To trigger immediately:

```bash
ssh ubuntu@mcp.vue-mcp.org "cd /opt/vue-mcp && docker compose --env-file .env.production \
  -f docker-compose.prod.yml exec -T ingestion vue-docs-ingest run --source {name} --verbose"
```

The server's hot reload (60s PG poll) will pick up the new data automatically.

## Deployment

The server is deployed as a Docker Compose stack on an Infomaniak OpenStack VM.

### Architecture

```
Internet -> Traefik (:80/:443, TLS via Let's Encrypt) -> MCP Server (:8000, streamable-http)
                                                              |-- PostgreSQL (shared data layer)
                                                              |-- Qdrant (vector search)
                                                              +-- Ingestion (self-scheduling, writes to PG + Qdrant)
```

### Services

| Service | Image | Purpose |
|---|---|---|
| `mcp-server` | `ghcr.io/.../vue-mcp-server` | FastMCP server (streamable-http transport) |
| `ingestion` | `ghcr.io/.../vue-mcp-ingestion` | Self-scheduling pipeline (`watch` command, runs every 24h) |
| `postgres` | `postgres:17-alpine` | Shared data: entities, synonyms, pages, BM25 model, index state |
| `qdrant` | `qdrant/qdrant:v1.17.0` | Vector database (dense + sparse hybrid search), collection: `vue_ecosystem` |
| `traefik` | `traefik:v3.6` | Reverse proxy, TLS, rate limiting (60 req/min, 10 concurrent, 100KB body) |

### Docker Images

One multi-target `Dockerfile` produces two images:
- **server**: `vue-docs-core` + `fastmcp` + `psycopg` + `sqlalchemy`. No git, no npm.
- **ingestion**: `vue-docs-core` + `typer` + `rich` + `psycopg` + `sqlalchemy` + `git`. No npm (TypeDoc generation skipped in Docker).

Build locally: `make docker-build`

### Data Flow

PostgreSQL is the shared data layer between ingestion (writes) and server (reads). No shared filesystem volumes for
application data. The `data/` directory is gitignored and only used for local development without PG.

### Docker Compose Files

| File | Services | Use case |
|---|---|---|
| `docker-compose.dev.yml` | postgres + qdrant (ports exposed, tmpfs) | Local dev, integration tests |
| `docker-compose.local.yml` | all services + Traefik (mkcert TLS) | Full local stack |
| `docker-compose.prod.yml` | all services + Traefik (Let's Encrypt) | Production deployment |

### Local Development with Docker

For development and integration tests, start just the infrastructure:

```bash
make docker-dev-up    # postgres:5432, qdrant:6333
make test-integration # runs integration-marked tests
```

For a full local stack with TLS:

```bash
mkcert -install
mkcert -cert-file certs/local.pem -key-file certs/local-key.pem "$(hostname -I | awk '{print $1}').nip.io"
DOMAIN=$(hostname -I | awk '{print $1}').nip.io make docker-local-up
```

### Production Deployment

```bash
make deploy   # syncs compose file + scripts, pulls latest GHCR images, restarts stack
```

The deploy script (`scripts/deploy.sh`) SCPs `docker-compose.prod.yml`, `backup.sh`, and `restore.sh` to the server,
then pulls images and restarts services. The `.env.production` file on the server (not in git) provides secrets and
`ENABLED_SOURCES`.

### Server Transport

The server supports two transport modes via `SERVER_TRANSPORT` env var:
- `stdio` (default): for local MCP client connections
- `streamable-http`: for production, serves on `SERVER_HOST:SERVER_PORT/mcp`

### Hot Reload

The server polls PostgreSQL every 60 seconds for data changes. When ingestion writes new entities, pages, or BM25
models, the server reloads them automatically with zero downtime.

### Backup & Restore

```bash
scripts/backup.sh [backup_dir]    # pg_dump + Qdrant snapshot (vue_ecosystem collection), 7-day rotation
scripts/restore.sh <dump.sql.gz> [snapshot]  # Restore from backup
```

### CI/CD

- `.github/workflows/ci.yml`: Lint + test on PRs
- `.github/workflows/build-and-push.yml`: Build both images, push to GHCR on push to main
- `scripts/deploy.sh`: SSH to VM, sync config files, pull images, restart stack

## Design Principles

- **Structure-aware chunking.** Respect the documentation's heading hierarchy (page -> section -> subsection -> block).
  Never use fixed-size token chunking.
- **Readable reconstruction.** Reassemble results into coherent mini-documents using metadata and sort keys, returned in
  documentation reading order, preserving the natural flow of the docs.
- **Deterministic where possible.** Entity extraction, cross-references, and markdown parsing use deterministic methods.
  Reserve LLM calls for enrichment and summarization at indexing time.
- **Hybrid retrieval.** Every search combines dense semantic embeddings, BM25 sparse search, and entity metadata
  boosting. No single retrieval method is trusted alone.
- **Unified embedding space.** All content types (prose, code, images, summaries, HyPE questions) share one embedding
  model (jina-embeddings-v5-text-small). No separate code or image embedding models.
- **Cost-conscious.** Per-query API cost must stay under $0.001. Favor token-based pricing, cheap LLMs for query-time
  tasks, and deterministic processing wherever possible.
- **Incremental by design.** Content hashing at every layer to skip unchanged files during re-indexing.
- **Adapter-driven multi-framework.** Each documentation source owns its customization via a SourceAdapter. The shared
  pipeline backbone handles change detection, enrichment, embedding, indexing, and state. No source-specific conditionals
  in the pipeline.

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

10. **Curated data as package code.** Static lookup tables (e.g., synonym tables, source definitions) live as Python
    dicts in `vue_docs_core.data`, not as external files.

## Testing

- **Framework:** pytest + pytest-asyncio, `asyncio_mode = "auto"`
- **Location:** `tests/` at repo root
- **Integration tests:** Marked with `@pytest.mark.integration`, skipped by default (require live API keys)
- **Mocking pattern:** Use `unittest.mock.AsyncMock` for FastMCP Context and async clients. Use `patch()` on client
  methods. Helper functions (`_mock_ctx()`, `_make_hit()`) over pytest fixtures for test data construction.
- **Adapter in tests:** When testing parsing on real Vue docs, pass `content_cleaner=VueAdapter().clean_content` to
  `parse_markdown_file()`. The generic parser does not do source-specific cleaning.
- **Test before commit:** `make test` must pass (or `make pr-ready` for the full check)

## Key Technical Decisions

| Decision | Rationale |
|---|---|
| SourceAdapter pattern | Each framework owns its customization hooks. Pipeline backbone stays generic. No conditionals per source. |
| Jina AI as unified search provider | Single vendor, single token pool, single embedding space |
| No LLM at query time | Per-query LLM cost + hallucination risk; vocab gap handled by HyPE at indexing time |
| Per-source BM25 models | Each library has distinct vocabulary and term frequencies. Shared BM25 would dilute IDF weights. |
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
| Jina AI | Embeddings (jina-embeddings-v5-text-small) + reranking (jina-reranker-v3) | `httpx` |
| Google Gemini | Contextual enrichment, HyPE generation, RAPTOR summaries (ingestion only, gemini-2.5-flash) | `google-genai` |
| Qdrant | Vector database (dense + sparse hybrid search), collection `vue_ecosystem` | `qdrant-client` |
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

**Ingestion** (offline, self-scheduled, per source): Clone/pull docs -> adapter.discover_files() -> parse into
structural chunks (adapter.clean_content()) -> extract entities + cross-refs -> enrich with contextual prefixes
(Gemini) -> generate HyPE questions (Gemini) -> embed all (Jina) -> generate BM25 sparse vectors -> upsert to Qdrant ->
save entities, synonyms, pages, BM25 model, and index state to PostgreSQL.

**Query** (online, per-request): Embed query (Jina) + BM25 sparse vector -> hybrid search (Qdrant: dense + BM25,
native RRF) -> resolve HyPE hits -> cross-reference expansion -> reranking (Jina) -> reconstruction (sort by reading
order, merge adjacent, format). No LLM calls at query time.

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
- Add source-specific conditionals in the pipeline. Use the SourceAdapter pattern instead.
- Hardcode Vue-specific logic in the generic markdown parser. Put it in the adapter's `clean_content()`.
