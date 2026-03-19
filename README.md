# Vue Docs MCP Server

An MCP (Model Context Protocol) server that gives AI assistants deep, structured access to the entire [Vue.js documentation](https://vuejs.org/). Instead of pasting docs into prompts or hoping the LLM's training data is up to date, connect this server and let your AI assistant search, browse, and retrieve Vue documentation on demand.

## What It Does

Ask your AI assistant any Vue question — it queries this server behind the scenes and gets back accurate, up-to-date documentation fragments with full context.

**Tools** — semantic search across all Vue docs:
- `vue_docs_search` — Find documentation for any Vue topic, concept, or error
- `vue_api_lookup` — Instant lookup for any Vue API (`ref`, `computed`, `v-model`, etc.)
- `vue_get_related` — Discover related APIs, concepts, and documentation pages

**Resources** — browse the documentation structure directly:
- `vue://topics` — Full table of contents
- `vue://pages/{path}` — Raw markdown of any documentation page
- `vue://api/index` — Complete API reference index
- `vue://api/entities/{name}` — Detailed info for a specific API
- `vue://scopes` — Available search scopes for narrowing queries

**Prompts** — guided workflows for common tasks:
- `debug_vue_issue` — Systematic debugging workflow
- `compare_vue_apis` — Side-by-side API comparison
- `migrate_vue_pattern` — Migration guide between Vue patterns

## How It Works

The server combines multiple retrieval strategies for high-quality results:

1. **Structure-aware chunking** — Vue docs are parsed respecting their heading hierarchy, keeping code examples paired with explanations
2. **Hybrid search** — Every query runs dense semantic search (Jina embeddings), BM25 keyword search, and API entity boosting simultaneously
3. **Query intelligence** — Questions are decomposed, rewritten, and expanded using Gemini Flash before retrieval
4. **Reranking** — Candidate results are reranked by Jina for precision
5. **Readable reconstruction** — Results are reassembled in documentation reading order, not just ranked by score

## Prerequisites

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **API keys** for:
  - [Jina AI](https://jina.ai/) — embeddings and reranking
  - [Google Gemini](https://ai.google.dev/) — query transformation and enrichment
  - [Qdrant](https://qdrant.tech/) — vector database (cloud or local)

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-org/vue-mcp.git
cd vue-mcp
make bootstrap    # Clones Vue docs + installs dependencies
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env with your API keys:
#   JINA_API_KEY=...
#   GEMINI_API_KEY=...
#   QDRANT_URL=...
#   QDRANT_API_KEY=...
```

### 3. Run the ingestion pipeline

This parses the Vue documentation, generates embeddings, and indexes everything into Qdrant:

```bash
make ingest       # Incremental (skips unchanged files)
make ingest-full  # Full re-index from scratch
```

### 4. Start the server

```bash
make serve
```

### 5. Connect your MCP client

Add the server to your MCP client configuration. For Claude Code, add to your MCP settings:

```json
{
  "mcpServers": {
    "vue-docs": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vue-mcp", "vue-docs-server"]
    }
  }
}
```

Then ask your AI assistant anything about Vue — it will use the server automatically.

## Project Structure

```
packages/
  core/       Shared library: models, clients, parsing, retrieval logic
  ingestion/  CLI tool for indexing Vue docs into the vector database
  server/     MCP server exposing tools, resources, and prompts
eval/         Evaluation suite for measuring retrieval quality
data/         Indexed data, entity dictionaries, BM25 models
tests/        Test suite
scripts/      Bootstrap and debug utilities
```

## Development

```bash
make help         # Show all available commands
make test         # Run tests (skips integration tests)
make test-all     # Run all tests (requires API keys)
make lint-fix     # Auto-fix lint issues
make format       # Apply code formatting
make pr-ready     # Lint + format + test (run before committing)
make check        # Lint + format check without modifications
```

Inspect how a specific markdown file gets chunked:

```bash
make inspect FILE=data/vue-docs/src/guide/essentials/computed.md
```

## Architecture

The system has two main pipelines:

**Ingestion** (offline) — Markdown files are parsed into structural chunks, enriched with contextual summaries and hypothetical questions (HyPE), embedded via Jina, and stored in Qdrant with both dense and BM25 sparse vectors.

**Query** (online) — Incoming queries go through entity extraction, intent classification, query transformation (parallel Gemini calls), hybrid search in Qdrant, cross-reference expansion, Jina reranking, and readable reconstruction.

### External Services

| Service | Role |
|---|---|
| [Jina AI](https://jina.ai/) | Embeddings (jina-embeddings-v4) and reranking (jina-reranker-v3) |
| [Google Gemini](https://ai.google.dev/) | Query transformation, contextual enrichment, HyPE generation |
| [Qdrant](https://qdrant.tech/) | Vector database with hybrid dense + sparse search |

## License

[FSL-1.1-ALv2](LICENSE.md) — Functional Source License, Version 1.1, with Apache License 2.0 future grant. Free for internal use, education, and research. Converts to Apache 2.0 two years after each release.
