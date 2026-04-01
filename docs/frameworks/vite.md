# Vite

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.95 / 5 composite score</span> &middot; 87.8% API recall &middot; 49 questions evaluated

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

## Benchmarks vs Context7

Evaluated on 49 Vite questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

::: info Methodology
Each question has a ground-truth answer with expected API names and documentation paths. Both providers receive the same question and return documentation context. The judge scores the retrieved context on relevance, completeness, correctness, API coverage, and conciseness. See the `eval/` directory in the repository for the full evaluation framework.
:::

### Overall Scores

<ClientOnly>
<ApexChart
  type="radar"
  height="400"
  :options="{
    chart: { toolbar: { show: false } },
    xaxis: { categories: ['Relevance', 'Completeness', 'Correctness', 'API Coverage', 'Conciseness'] },
    yaxis: { min: 0, max: 5, tickAmount: 5 },
    colors: ['#42b883', '#f97316'],
    legend: { position: 'bottom' },
    markers: { size: 4 },
  }"
  :series="[
    { name: 'Vue Docs MCP', data: [5.00, 4.92, 4.96, 4.86, 5.00] },
    { name: 'Context7', data: [4.94, 4.53, 4.80, 4.31, 4.78] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **5.00** | 4.94 |
| Completeness | **4.92** | 4.53 |
| Correctness | **4.96** | 4.80 |
| API Coverage | **4.86** | 4.31 |
| Conciseness | **5.00** | 4.78 |
| **Composite** | **4.95** | **4.67** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| API Recall | **87.8%** | 84.7% |
| Avg Response Tokens | 4,103 | 943 |
| Avg Latency | **0.91s** | 1.84s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
