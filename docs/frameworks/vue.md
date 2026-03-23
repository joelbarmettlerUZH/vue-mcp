# Vue.js

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.82 / 5 composite score</span> &middot; 98.7% API recall &middot; 173 questions evaluated

Vue Docs MCP provides deep access to the official [Vue.js documentation](https://vuejs.org), covering the core framework, Composition API, Options API, built-in components, directives, and the full API reference.

## Activation

Vue.js is enabled by default. No action needed.

## Tools

### `vue_docs_search`

Semantic search over Vue.js documentation. Uses a 6-step pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `guide/essentials`, `guide/components`, `guide/reusability`, `guide/built-ins`, `guide/scaling-up`, `guide/best-practices`, `guide/typescript`, `guide/extras`, `api`, `tutorial`, `examples`, `glossary`, `style-guide`

### `vue_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the API reference.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `ref`, `onMounted`, `v-model`) |

### `vue_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vue://topics` | Full table of contents |
| `vue://topics/{section}` | TOC for a specific section (e.g. `vue://topics/guide/essentials`) |
| `vue://pages/{path}` | Raw markdown of any doc page (e.g. `vue://pages/guide/essentials/reactivity-fundamentals`) |
| `vue://api/index` | Complete API entity index grouped by type |
| `vue://api/entities/{name}` | Details for a specific API (e.g. `vue://api/entities/ref`) |
| `vue://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vue_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_vue_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `ref, reactive` or `v-if, v-show`) |
| `migrate_vue_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. Options API to Composition API) |

## Benchmarks vs Context7

Evaluated on 173 Vue.js questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.93, 4.83, 4.87, 4.53, 4.95] },
    { name: 'Context7', data: [2.09, 1.67, 1.86, 1.90, 4.55] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.93** | 2.09 |
| Completeness | **4.83** | 1.67 |
| Correctness | **4.87** | 1.86 |
| API Coverage | **4.53** | 1.90 |
| Conciseness | 4.95 | 4.55 |
| **Composite** | **4.82** | **2.41** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| API Recall | **98.7%** | 53.1% |
| Avg Response Tokens | 4,213 | 1,739 |
| Avg Latency | **1.44s** | 1.72s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Pass Rates

Percentage of questions where **all** judge dimensions scored at or above the threshold:

| Threshold | Vue Docs MCP | Context7 |
|---|---|---|
| All dimensions >= 5 | **83.8%** | 6.4% |
| All dimensions >= 4 | **86.7%** | 9.2% |
| All dimensions >= 3 | **88.4%** | 13.3% |
| All dimensions >= 2 | **90.8%** | 23.7% |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- Context7 sometimes returns Vue 2 content for Vue 3 questions, which affects its scores.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
