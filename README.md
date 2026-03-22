<p align="center">
  <img src="docs/public/logo.svg" width="80" alt="Vue Docs MCP">
</p>

<h1 align="center">Vue Docs MCP</h1>

<p align="center">
  Up-to-date Vue ecosystem documentation for any AI assistant
</p>

<p align="center">
  <a href="https://vue-mcp.org">Website</a> &middot;
  <a href="https://vue-mcp.org/guide/getting-started">Getting Started</a> &middot;
  <a href="https://vue-mcp.org/clients/">MCP Clients</a> &middot;
  <a href="https://vue-mcp.org/reference/tools">API Reference</a>
</p>

<p align="center">
  <a href="https://vue-mcp.org/clients/cursor">
    <img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Install MCP Server" height="32">
  </a>
</p>

<p align="center">
  <a href="https://github.com/joelbarmettlerUZH/vue-mcp/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/joelbarmettlerUZH/vue-mcp/ci.yml?label=tests&labelColor=212121" alt="Tests"></a>
  <a href="LICENSE.md"><img src="https://img.shields.io/badge/license-FSL--1.1--ALv2-blue?labelColor=212121" alt="License"></a>
</p>

---

## The Problem

LLMs have a knowledge cutoff. The Vue ecosystem evolves. When you ask your AI assistant about Vue:

- Code examples are outdated and based on old training data
- Hallucinated APIs that don't exist in the current version
- No way to cite or verify answers against the official docs

## The Solution

Vue Docs MCP gives your AI assistant direct access to the [Vue ecosystem documentation](https://vuejs.org/) through the [Model Context Protocol](https://modelcontextprotocol.io/). Every answer is grounded in the official docs.

The hosted server at **`mcp.vue-mcp.org`** is free. No API keys, no setup required.

## Supported Frameworks

| Framework | Status | Description |
|---|---|---|
| [Vue.js](https://vuejs.org) | :white_check_mark: Available | Core framework: reactivity, components, Composition API |
| [Vue Router](https://router.vuejs.org) | :construction: In progress | Official router: navigation guards, dynamic routes |
| [Pinia](https://pinia.vuejs.org) | :calendar: Planned | Official state management |
| [VueUse](https://vueuse.org) | :calendar: Planned | Composition API utilities |
| [Nuxt](https://nuxt.com) | :calendar: Planned | Full-stack framework |
| [Vuetify](https://vuetifyjs.com) | :calendar: Planned | Material Design component library |
| [Vite](https://vite.dev) | :calendar: Planned | Build tool |
| [Vitest](https://vitest.dev) | :calendar: Planned | Unit testing framework |
| [VitePress](https://vitepress.dev) | :calendar: Planned | Static site generator |

Each framework gets its own tools, resources, and prompts. [Learn more about framework preferences](https://vue-mcp.org/reference/frameworks).

## Quick Start

### Claude Code

```bash
claude mcp add --scope user vue-docs --transport streamable-http https://mcp.vue-mcp.org/mcp
```

### Cursor

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=vue-docs&config=eyJ1cmwiOiJodHRwczovL21jcC52dWUtbWNwLm9yZy9tY3AifQ%3D%3D)

Or add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

### Other Clients

For Claude Desktop, Windsurf, VS Code, JetBrains, Zed, ChatGPT, and more, see the **[full client list](https://vue-mcp.org/clients/)**.

Any MCP client that supports streamable HTTP works with:

```
https://mcp.vue-mcp.org/mcp
```

## What's Included

**Tools** (per-framework, shown for Vue.js):

| Tool | Description |
|---|---|
| `vue_docs_search` | Find documentation for any Vue topic, concept, or error |
| `vue_api_lookup` | Instant lookup for any Vue API (`ref`, `computed`, `v-model`, etc.) |
| `vue_get_related` | Discover related APIs, concepts, and documentation pages |

When multiple frameworks are enabled, an `ecosystem_search` tool searches across all of them at once.

**Resources** (per-framework, shown for Vue.js):

| Resource | Description |
|---|---|
| `vue://topics` | Full table of contents |
| `vue://pages/{path}` | Raw markdown of any documentation page |
| `vue://api/index` | Complete API reference index |
| `vue://api/entities/{name}` | Detailed info for a specific API |
| `vue://scopes` | Available search scopes for narrowing queries |

**Prompts** (guided workflows):

| Prompt | Description |
|---|---|
| `debug_vue_issue` | Systematic debugging workflow |
| `compare_vue_apis` | Side-by-side API comparison |
| `migrate_vue_pattern` | Migration guide between Vue patterns |

## Comparison with Context7

### Feature Comparison

| Feature | Vue Docs MCP | Context7 |
|---|---|---|
| Tailored to Vue ecosystem | :white_check_mark: Purpose-built | General-purpose (9000+ libraries) |
| Browsable resources (TOC, pages, API index) | :white_check_mark: Full enumeration | :x: |
| Guided prompts (debug, compare, migrate) | :white_check_mark: 3 workflows | :x: |
| API entity lookup with fuzzy matching | :white_check_mark: | :x: |
| Self-hostable | :white_check_mark: Docker Compose | :x: |
| Open source | :white_check_mark: | :white_check_mark: |
| Cost to user | Free | $10/seat (5000 calls) |

### Benchmark: LLM-as-Judge (173 questions, Gemini judge, temperature 0)

#### Overall Scores (1-5 scale, higher is better)

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.93** :trophy: | 2.09 |
| Completeness | **4.83** :trophy: | 1.67 |
| Correctness | **4.87** :trophy: | 1.86 |
| API Coverage | **4.53** :trophy: | 1.90 |
| Conciseness | 4.95 | **4.55** |
| **Composite** | **4.82** :trophy: | **2.41** |

#### Scores by Difficulty

| Difficulty | Vue Docs MCP | Context7 |
|---|---|---|
| Easy (29 questions) | **4.87** :trophy: | 2.75 |
| Medium (27 questions) | **4.84** :trophy: | 2.24 |
| Hard (66 questions) | **4.89** :trophy: | 2.20 |
| Extreme (51 questions) | **4.69** :trophy: | 2.58 |

#### Scores by Question Type

| Intent | Vue Docs MCP | Context7 |
|---|---|---|
| API Lookup (18 questions) | **4.93** :trophy: | 2.17 |
| How-To (62 questions) | **4.86** :trophy: | 2.43 |
| Debugging (41 questions) | **4.82** :trophy: | 2.17 |
| Comparison (20 questions) | **4.83** :trophy: | 2.75 |
| Conceptual (30 questions) | **4.65** :trophy: | 2.56 |

#### Retrieval Metrics

| Metric | Vue Docs MCP | Context7   |
|---|---|------------|
| API Recall | **98.7%** :trophy: | 53.1%      |
| Avg Response Tokens | 4,213 | **1,739** trophy: |
| Avg Latency | **1.44s** :trophy: | 1.72s      |
| Cost per Query (internal) | $0.0003 | N/A        |
| Cost per Query (external) | **Free** :trophy: | $0.002     |

<details>
<summary>About this benchmark</summary>

The evaluation uses 173 Vue.js questions across 6 intent types and 4 difficulty levels. Each question has ground-truth answers with expected API names and documentation paths. An LLM judge (Gemini, temperature 0) scores retrieved documentation on relevance, completeness, correctness, API coverage, and conciseness. API recall measures whether expected API names appear in the response. See the `eval/` directory for the full evaluation framework.

Context7's lower scores are partly explained by its general-purpose design (9000+ libraries) vs our Vue-specific optimization. Context7 also returns Vue 2 content for some Vue 3 questions. Path recall (97% vs 0.6%) is structurally biased since our ground truth uses `vuejs.org` paths, so it is excluded from this comparison.
</details>

## How It Works

The server combines multiple retrieval strategies for high-quality results:

1. **Structure-aware chunking.** Docs are parsed respecting their heading hierarchy, keeping code examples paired with explanations.
2. **Hybrid search.** Every query runs dense semantic search (Jina embeddings) and BM25 keyword search simultaneously.
3. **Smart entity detection.** API names detected with typo tolerance, synonym lookup, and fuzzy matching.
4. **Cross-reference expansion.** Related documentation sections are automatically pulled in.
5. **Reranking.** Candidates reranked by Jina for precision.
6. **Readable reconstruction.** Results reassembled in documentation reading order, preserving the natural flow of the docs.

No LLM is used at query time. See **[How It Works](https://vue-mcp.org/reference/how-it-works)** for the full technical breakdown.

## Self-Hosting

If you prefer to run your own instance, see the **[Self-Hosting guide](https://vue-mcp.org/guide/self-hosting)** or the quick version below.

### Prerequisites

- Python 3.13+, [uv](https://docs.astral.sh/uv/)
- API keys: [Jina AI](https://jina.ai/), [Google Gemini](https://ai.google.dev/), [Qdrant](https://qdrant.tech/)

### Setup

```bash
git clone https://github.com/joelbarmettlerUZH/vue-mcp.git
cd vue-mcp
make bootstrap          # Clone Vue docs + install deps
cp .env.example .env    # Add your API keys
make ingest             # Index the documentation
make serve              # Start the MCP server
```

Connect via stdio transport:

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

### Docker

```bash
cp .env.production.example .env.production  # Configure
make docker-build && make docker-prod-up     # Build & start full stack
```

## Development

```bash
make help         # Show all available commands
make test         # Run tests (skips integration tests)
make pr-ready     # Lint + format + test (run before committing)
make docs         # Start docs dev server
```

## Documentation

Full documentation at **[vue-mcp.org](https://vue-mcp.org)**:

- [Getting Started](https://vue-mcp.org/guide/getting-started): Connect in 30 seconds
- [MCP Clients](https://vue-mcp.org/clients/): Setup guides for 10+ clients
- [Tools Reference](https://vue-mcp.org/reference/tools): Search tools, parameters, scopes
- [Resources & Prompts](https://vue-mcp.org/reference/resources): Browse docs, guided workflows
- [How It Works](https://vue-mcp.org/reference/how-it-works): Ingestion and query pipeline internals
- [Self-Hosting](https://vue-mcp.org/guide/self-hosting): Run your own instance

## License

[FSL-1.1-ALv2](LICENSE.md). Functional Source License, Version 1.1, with Apache License 2.0 future grant. Free for internal use, education, and research. Converts to Apache 2.0 two years after each release.
