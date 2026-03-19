# Vue Documentation MCP Server

MCP server providing semantic search and retrieval over Vue.js documentation. Combines dense embeddings (Jina), sparse
search (BM25), and LLM query transformation (Gemini) to return structure-aware, readable documentation fragments.

## Repository Structure

```
packages/
  core/       Shared library: models, clients (Jina, Qdrant, Gemini, BM25), parsing, retrieval
  ingestion/  CLI tool (Typer): scan → parse → enrich → embed → store
  server/     MCP server (FastMCP): tools, resources, prompts, query pipeline
eval/         Evaluation suite (separate package, not shipped)
data/         Shared state between ingestion and server (entity dict, synonym table, BM25 model)
tests/        Root-level pytest suite
scripts/      Bootstrap and debug utilities
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

For single-file test runs: `uv run pytest tests/test_server.py -v`

## Verification

Before committing, always run:

```bash
make pr-ready
```

## Design Principles

- **Structure-aware chunking.** Respect the documentation's heading hierarchy (page → section → subsection → block).
  Never use fixed-size token chunking.
- **Readable reconstruction.** Reassemble results into coherent mini-documents using metadata and sort keys, returned in
  documentation reading order — not ranked by score alone.
- **Deterministic where possible.** Entity extraction, cross-references, and markdown parsing use deterministic methods.
  Reserve LLM calls for enrichment, summarization, and query transformation.
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
   model, Qdrant client). Initialized at server startup, accessed by tools.

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
| No HyDE at query time | Per-query LLM cost + hallucination risk; vocab gap handled by HyPE at indexing time |
| Gemini Flash Lite for query-time LLM | ~$0.00025 for 3 parallel transformation calls |
| `bm25s` for sparse vectors | Lightweight, no external API needed |
| `markdown-it-py` for parsing | Token/tree API, heading hierarchy, code blocks, links, images |
| `rapidfuzz` for entity matching | Sub-millisecond fuzzy matching with typo tolerance |
| FastMCP with middleware | Error handling, timing, response limiting as composable layers |

## External Services

| Service | Purpose | Client |
|---|---|---|
| Jina AI | Embeddings (jina-embeddings-v4) + reranking (jina-reranker-v3) | `httpx` |
| Google Gemini | Query transformation, contextual enrichment, HyPE generation | `google-genai` |
| Qdrant | Vector database (dense + sparse hybrid search) | `qdrant-client` |

API keys configured via `.env` (see `.env.example`). All API calls go through async clients in
`packages/core/src/vue_docs_core/clients/`.

## Ruff Configuration

Ruff handles both linting and formatting. Config lives in root `pyproject.toml`:
- Line length: 100
- Target: Python 3.13
- Rules: E, W, F, I, UP, B, SIM, TCH, RUF
- Quote style: double
- isort knows: `vue_docs_core`, `vue_docs_ingestion`, `vue_docs_server`

Don't manually enforce style rules — run `make lint-fix && make format` instead.

## Data Flow

**Ingestion** (offline, batch): Markdown files → parse into structural chunks → extract entities + cross-refs → enrich
with contextual prefixes (Gemini) → generate HyPE questions (Gemini) → embed all (Jina) → generate BM25 sparse vectors
→ upsert to Qdrant. State tracked in `data/state/index_state.json`.

**Query** (online, per-request): Entity extraction (deterministic) → intent classification → query transformation
(Gemini, parallel) → hybrid search (Qdrant: dense + BM25 + entity boost) → RRF fusion → cross-reference expansion →
reranking (Jina) → reconstruction (sort by reading order, merge adjacent, format).

## Do Not

- Add LangChain, LlamaIndex, or similar orchestration frameworks. Use direct HTTP clients instead.
- Use fixed-size token chunking. Chunk at structural boundaries (headings).
- Store HyPE embeddings as additional vectors on existing points. Store them as separate Qdrant points with
  `parent_chunk_id`.
- Edit `uv.lock` manually. Use `uv add/remove` for dependency changes.
- Commit `.env` or API keys. Use `.env.example` as the template.
- Return empty results from search tools. Always fall back to broader scope or RAPTOR summary nodes.
