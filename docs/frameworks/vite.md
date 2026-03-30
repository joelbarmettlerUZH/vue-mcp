# Vite

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.94 / 5 composite score</span> &middot; 87.8% API recall &middot; 49 questions evaluated

Vue Docs MCP provides deep access to the official [Vite documentation](https://vite.dev), covering the build tool's configuration reference, plugin API, HMR API, JavaScript API, Environment API, and migration guides.

## Activation

Vite is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(vite=true)
```

## Tools

### `vite_docs_search`

Semantic search over Vite documentation. Uses a 6-step pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `config`, `changes`, `plugins`

### `vite_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `defineConfig`, `createServer`, `server.proxy`) |

### `vite_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vite://topics` | Full table of contents |
| `vite://topics/{section}` | TOC for a specific section (e.g. `vite://topics/guide`) |
| `vite://pages/{path}` | Raw markdown of any doc page (e.g. `vite://pages/config/shared-options`) |
| `vite://api/index` | Complete API entity index grouped by type |
| `vite://api/entities/{name}` | Details for a specific API (e.g. `vite://api/entities/defineConfig`) |
| `vite://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vite_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_vite_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `server.proxy, server.middlewareMode`) |
| `migrate_vite_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. Vite 5 to Vite 6) |

## Benchmarks

Evaluated on 49 Vite questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

::: info Methodology
Each question has a ground-truth answer with expected API names and documentation paths. The provider receives the question and returns documentation context. The judge scores the retrieved context on relevance, completeness, correctness, API coverage, and conciseness. See the `eval/` directory in the repository for the full evaluation framework.
:::

### Overall Scores

| Metric | Score |
|---|---|
| Relevance | **5.00** |
| Completeness | **4.88** |
| Correctness | **4.92** |
| API Coverage | **4.88** |
| Conciseness | **4.98** |
| **Composite** | **4.94** |

### Retrieval and Cost

| Metric | Value |
|---|---|
| Path Recall | **100%** |
| API Recall | **87.8%** |
| Avg Response Tokens | 4,115 |
| Avg Latency | **0.91s** |
| Cost per Query (user-facing) | **Free** |

### Pass Rates

Percentage of questions where **all** judge dimensions scored at or above the threshold:

| Threshold | Pass Rate |
|---|---|
| All dimensions >= 5 | **96%** |
| All dimensions >= 4 | **96%** |
| All dimensions >= 3 | **96%** |
| All dimensions >= 2 | **96%** |
