# Pinia Colada

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.83 / 5 composite score</span> &middot; 93.9% API recall &middot; 49 questions evaluated

Vue Docs MCP provides deep access to the official [Pinia Colada documentation](https://pinia-colada.esm.dev), covering the smart data-fetching layer for Vue: queries, mutations, infinite queries, the query/mutation cache, the `defineQuery` factory pattern, the official plugin set, and migration paths from TanStack Query (Vue Query).

::: tip Pairs with Pinia
Pinia Colada is built on Pinia and shares its devtools and reactivity. Activate both frameworks together for the best experience: `set_framework_preferences(pinia=true, pinia_colada=true)`.
:::

## Activation

Pinia Colada is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(pinia_colada=true)
```

## Tools

### `pinia_colada_docs_search`

Semantic search over Pinia Colada documentation. Uses the standard 6-step retrieval pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `advanced`, `cookbook`, `plugins`

### `pinia_colada_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_name` | `string` | | API name to look up (e.g. `useQuery`, `defineQuery`, `useQueryCache`, `PiniaColadaRetry`) |

### `pinia_colada_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `topic` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `pinia-colada://topics` | Full table of contents |
| `pinia-colada://topics/{section}` | TOC for a specific section (e.g. `pinia-colada://topics/guide`) |
| `pinia-colada://pages/{path}` | Raw markdown of any doc page (e.g. `pinia-colada://pages/guide/queries`) |
| `pinia-colada://api/index` | Complete API entity index grouped by type |
| `pinia-colada://api/entities/{name}` | Details for a specific API (e.g. `pinia-colada://api/entities/useQuery`) |
| `pinia-colada://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_pinia_colada_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_pinia_colada_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `useQuery, defineQuery`) |
| `migrate_pinia_colada_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. TanStack Query to Pinia Colada) |

## Coverage

| Area | What's indexed |
|---|---|
| Query composables | `useQuery`, `useQueryState`, `useInfiniteQuery`, `useQueryCache` |
| Mutation composables | `useMutation`, `useMutationCache` |
| Definition helpers | `defineQuery`, `defineQueryOptions`, `defineMutation`, `defineMutationOptions`, `defineInfiniteQueryOptions` |
| Cache & SSR | `hydrateQueryCache`, `serializeQueryCache`, `setInfiniteQueryData`, `toCacheKey`, `EntryKey` |
| Plugin system | `PiniaColadaPlugin`, `PiniaColadaPluginContext`, plugin authoring API |
| Official plugins | Retry, Auto-refetch, Delay, Cache Persister, Query Hooks, TanStack Compat |
| Type extension | `TypesConfig`, `QueryMeta`, `MutationMeta`, tagged keys (`EntryKeyTagged`) |
| Concepts | Query keys, query invalidation, optimistic updates, error handling, cancelling queries, paginated queries, placeholder data, SSR, testing, prefetching |
| Migration | TanStack Query / Vue Query migration with codemods + compat plugin |
| Nuxt | `@pinia/colada-nuxt` module setup |

## Benchmarks vs Context7

Evaluated on 49 Pinia Colada questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.82, 4.80, 4.80, 4.78, 4.96] },
    { name: 'Context7', data: [4.88, 4.73, 4.82, 4.78, 4.88] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | 4.82 | **4.88** |
| Completeness | **4.80** | 4.73 |
| Correctness | 4.80 | **4.82** |
| API Coverage | 4.78 | 4.78 |
| Conciseness | **4.96** | 4.88 |
| **Composite** | **4.83** | 4.82 |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **98.0%** | 91.8% |
| API Recall | **93.9%** | 92.9% |
| Avg Response Tokens | 3,849 | **980** |
| Avg Latency | **1.64s** | 1.73s |
| P95 Latency | 6.88s | **2.15s** |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
