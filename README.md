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
  <a href="https://vue-mcp.org/frameworks/">Frameworks</a> &middot;
  <a href="https://vue-mcp.org/clients/">MCP Clients</a>
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

| Framework | Status |
|---|---|
| [Vue.js](https://vuejs.org) | Available |
| [Vue Router](https://router.vuejs.org) | Available |
| [VueUse](https://vueuse.org) | Available |
| [Vite](https://vite.dev), [Vitest](https://vitest.dev), [Nuxt](https://nuxt.com), [Pinia](https://pinia.vuejs.org), and [13 more](https://vue-mcp.org/frameworks/) | Planned |

Each framework gets its own tools, resources, and prompts. [See all frameworks](https://vue-mcp.org/frameworks/).

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

**Tools** (per framework):

| Tool | Description |
|---|---|
| `{framework}_docs_search` | Semantic search over the framework's documentation |
| `{framework}_api_lookup` | Instant API reference lookup with fuzzy matching |
| `{framework}_get_related` | Discover related APIs, concepts, and documentation pages |
| `ecosystem_search` | Cross-framework search (when 2+ frameworks enabled) |

**Resources** (per framework):

| Resource | Description |
|---|---|
| `{framework}://topics` | Full table of contents |
| `{framework}://pages/{path}` | Raw markdown of any documentation page |
| `{framework}://api/index` | Complete API reference index |
| `{framework}://api/entities/{name}` | Detailed info for a specific API |
| `{framework}://scopes` | Available search scopes |

**Prompts** (per framework):

| Prompt | Description |
|---|---|
| `debug_{framework}_issue` | Systematic debugging workflow |
| `compare_{framework}_apis` | Side-by-side API comparison |
| `migrate_{framework}_pattern` | Migration guide between patterns |

## Benchmarks

Evaluated by an LLM judge (Gemini, temperature 0) scoring retrieved documentation on relevance, completeness, correctness, API coverage, and conciseness (1-5 scale).

| Framework | Questions | Vue Docs MCP | Context7 |
|---|---|---|---|
| Vue.js | 173 | **4.82** | 2.41 |
| Vue Router | 49 | **4.78** | 3.33 |
| VueUse | 50 | **4.89** | 4.04 |

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| API Recall (Vue.js) | **98.7%** | 53.1% |
| API Recall (Vue Router) | **88.8%** | 34.4% |
| API Recall (VueUse) | **100.0%** | 92.0% |
| Cost per query | Free | $0.002 |

<details>
<summary>About this benchmark</summary>

Each question has ground-truth answers with expected API names and documentation paths. An LLM judge scores the retrieved documentation context. API recall measures whether expected API names appear in the response. See the `eval/` directory and framework pages for the full breakdown by difficulty, question type, and judge dimension.

Context7 is a general-purpose documentation server covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem. The comparison shows the quality advantage of specialization, but Context7's breadth is a genuine strength for multi-ecosystem projects. Context7 also returns Vue 2 content for some Vue 3 questions, which affects its scores.

Run `make eval-compare` to reproduce these results.
</details>

## How It Works

1. **Structure-aware chunking.** Docs are parsed respecting their heading hierarchy, keeping code examples paired with explanations.
2. **Hybrid search.** Every query runs dense semantic search (Jina embeddings) and BM25 keyword search simultaneously.
3. **Smart entity detection.** API names detected with typo tolerance, synonym lookup, and fuzzy matching.
4. **Cross-reference expansion.** Related documentation sections are automatically pulled in.
5. **Reranking.** Candidates reranked by Jina for precision.
6. **Readable reconstruction.** Results reassembled in documentation reading order.

No LLM is used at query time. See **[How It Works](https://vue-mcp.org/reference/how-it-works)** for the full technical breakdown.

## Self-Hosting

```bash
git clone https://github.com/joelbarmettlerUZH/vue-mcp.git
cd vue-mcp
make bootstrap          # Clone Vue docs + install deps
cp .env.example .env    # Add your API keys
make ingest             # Index the documentation
make serve              # Start the MCP server
```

See the **[Self-Hosting guide](https://vue-mcp.org/guide/self-hosting)** for Docker Compose deployment and configuration details.

## Development

```bash
make help         # Show all available commands
make test         # Run tests (skips integration tests)
make pr-ready     # Lint + format + test (run before committing)
```

## Documentation

Full documentation at **[vue-mcp.org](https://vue-mcp.org)**:

- [Getting Started](https://vue-mcp.org/guide/getting-started): Connect in 30 seconds
- [Supported Frameworks](https://vue-mcp.org/frameworks/): Tools, benchmarks, and roadmap per framework
- [MCP Clients](https://vue-mcp.org/clients/): Setup guides for 10+ clients
- [How It Works](https://vue-mcp.org/reference/how-it-works): Ingestion and query pipeline internals
- [Self-Hosting](https://vue-mcp.org/guide/self-hosting): Run your own instance

## License

[FSL-1.1-ALv2](LICENSE.md). Functional Source License, Version 1.1, with Apache License 2.0 future grant. Free for internal use, education, and research. Converts to Apache 2.0 two years after each release.
