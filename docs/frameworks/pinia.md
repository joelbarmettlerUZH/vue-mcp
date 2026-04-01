# Pinia

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.81 / 5 composite score</span> &middot; 100% API recall &middot; 49 questions evaluated

Vue Docs MCP provides deep access to the official [Pinia documentation](https://pinia.vuejs.org), covering the state management library's store definition (defineStore), state, getters, actions, plugins, Options API helpers, SSR, testing, and migration guides.

## Activation

Pinia is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(pinia=true)
```

## Tools

### `pinia_docs_search`

Semantic search over Pinia documentation. Uses a 6-step pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `core-concepts`, `cookbook`, `ssr`

### `pinia_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `defineStore`, `storeToRefs`, `$patch`) |

### `pinia_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `pinia://topics` | Full table of contents |
| `pinia://topics/{section}` | TOC for a specific section (e.g. `pinia://topics/core-concepts`) |
| `pinia://pages/{path}` | Raw markdown of any doc page (e.g. `pinia://pages/core-concepts/state`) |
| `pinia://api/index` | Complete API entity index grouped by type |
| `pinia://api/entities/{name}` | Details for a specific API (e.g. `pinia://api/entities/defineStore`) |
| `pinia://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_pinia_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_pinia_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `mapState, mapWritableState` or `$patch, $reset`) |
| `migrate_pinia_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. Vuex to Pinia) |

## Benchmarks vs Context7

Evaluated on 49 Pinia questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.92, 4.86, 4.86, 4.43, 4.98] },
    { name: 'Context7', data: [4.90, 4.65, 4.82, 4.20, 4.82] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.92** | 4.90 |
| Completeness | **4.86** | 4.65 |
| Correctness | **4.86** | 4.82 |
| API Coverage | **4.43** | 4.20 |
| Conciseness | **4.98** | 4.82 |
| **Composite** | **4.81** | **4.68** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| API Recall | **100%** | 93.9% |
| Avg Response Tokens | 4,361 | 972 |
| Avg Latency | **0.94s** | 1.74s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
