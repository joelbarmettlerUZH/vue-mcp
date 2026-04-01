# Nuxt

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.80 / 5 composite score</span> &middot; 100% API recall &middot; 49 questions evaluated

Vue Docs MCP provides deep access to the official [Nuxt documentation](https://nuxt.com), covering the full-stack framework's composables (useFetch, useAsyncData, useHead), components (NuxtLink, NuxtPage, NuxtLayout), configuration, directory structure, modules, and migration guides.

## Activation

Nuxt is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(nuxt=true)
```

## Tools

### `nuxt_docs_search`

Semantic search over Nuxt documentation. Uses a 6-step pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `getting-started`, `directory-structure`, `guide`, `api`, `bridge`, `migration`

### `nuxt_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `useFetch`, `NuxtLink`, `definePageMeta`) |

### `nuxt_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `nuxt://topics` | Full table of contents |
| `nuxt://topics/{section}` | TOC for a specific section (e.g. `nuxt://topics/api`) |
| `nuxt://pages/{path}` | Raw markdown of any doc page (e.g. `nuxt://pages/api/composables/use-fetch`) |
| `nuxt://api/index` | Complete API entity index grouped by type |
| `nuxt://api/entities/{name}` | Details for a specific API (e.g. `nuxt://api/entities/useFetch`) |
| `nuxt://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_nuxt_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_nuxt_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `useFetch, useAsyncData` or `useState, useCookie`) |
| `migrate_nuxt_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. Nuxt 2 to Nuxt 3) |

## Benchmarks vs Context7

Evaluated on 49 Nuxt questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.96, 4.82, 4.90, 4.37, 4.94] },
    { name: 'Context7', data: [4.98, 4.61, 4.84, 3.94, 4.76] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | 4.96 | **4.98** |
| Completeness | **4.82** | 4.61 |
| Correctness | **4.90** | 4.84 |
| API Coverage | **4.37** | 3.94 |
| Conciseness | **4.94** | 4.76 |
| **Composite** | **4.80** | **4.62** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| API Recall | **100%** | 89.8% |
| Avg Response Tokens | 3,689 | 924 |
| Avg Latency | **1.10s** | 1.64s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
