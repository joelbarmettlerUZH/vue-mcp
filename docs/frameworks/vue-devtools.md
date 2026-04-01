# Vue DevTools

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.37 / 5 composite score</span> &middot; 100% API recall &middot; 50 questions evaluated

Vue Docs MCP provides deep access to the official [Vue DevTools documentation](https://devtools.vuejs.org), covering installation (Vite plugin, browser extension, standalone), features, plugin API (addCustomTab, addCustomCommand), and migration guides.

## Activation

Vue DevTools is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(vue_devtools=true)
```

## Tools

### `vue_devtools_docs_search`

Semantic search over Vue DevTools documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `getting-started`, `guide`, `plugins`, `help`

### `vue_devtools_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `addCustomTab`, `onDevToolsClientConnected`) |

### `vue_devtools_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vue-devtools://topics` | Full table of contents |
| `vue-devtools://pages/{path}` | Raw markdown of any doc page |
| `vue-devtools://api/index` | Complete API entity index |
| `vue-devtools://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vue_devtools_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow |
| `compare_vue_devtools_apis` | `items` (comma-separated) | Side-by-side comparison |
| `migrate_vue_devtools_pattern` | `from_pattern`, `to_pattern` | Migration guide (e.g. v6 to v7) |

## Benchmarks vs Context7

Evaluated on 50 Vue DevTools questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.82, 4.66, 4.70, 3.16, 4.50] },
    { name: 'Context7', data: [3.18, 2.98, 3.10, 2.68, 4.68] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.82** | 3.18 |
| Completeness | **4.66** | 2.98 |
| Correctness | **4.70** | 3.10 |
| API Coverage | **3.16** | 2.68 |
| Conciseness | 4.50 | **4.68** |
| **Composite** | **4.37** | **3.32** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **99.0%** | 62.0% |
| API Recall | **100%** | 100% |
| Avg Response Tokens | 2,018 | 840 |
| Avg Latency | **0.70s** | 1.53s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- Context7 has limited coverage for Vue DevTools (37 code snippets), which significantly affects its scores.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
