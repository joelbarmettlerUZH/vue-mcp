# Vitest

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.77 / 5 composite score</span> &middot; 98.0% API recall &middot; 50 questions evaluated

Vue Docs MCP provides deep access to the official [Vitest documentation](https://vitest.dev), covering the test framework's API reference (test, describe, expect, vi), configuration options, mocking guides, browser testing, coverage, and migration guides.

## Activation

Vitest is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(vitest=true)
```

## Tools

### `vitest_docs_search`

Semantic search over Vitest documentation. Uses a 6-step pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `api`, `config`

### `vitest_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `vi.mock`, `test.each`, `expect`, `coverage`) |

### `vitest_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vitest://topics` | Full table of contents |
| `vitest://topics/{section}` | TOC for a specific section (e.g. `vitest://topics/guide`) |
| `vitest://pages/{path}` | Raw markdown of any doc page (e.g. `vitest://pages/api/vi`) |
| `vitest://api/index` | Complete API entity index grouped by type |
| `vitest://api/entities/{name}` | Details for a specific API (e.g. `vitest://api/entities/vi.mock`) |
| `vitest://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vitest_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_vitest_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `vi.mock, vi.doMock` or `test.each, test.for`) |
| `migrate_vitest_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. Jest to Vitest) |

## Benchmarks vs Context7

Evaluated on 50 Vitest questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.82, 4.66, 4.72, 4.70, 4.96] },
    { name: 'Context7', data: [4.92, 4.80, 4.86, 4.56, 4.86] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | 4.82 | **4.92** |
| Completeness | 4.66 | **4.80** |
| Correctness | 4.72 | **4.86** |
| API Coverage | **4.70** | 4.56 |
| Conciseness | **4.96** | 4.86 |
| **Composite** | **4.77** | **4.80** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| API Recall | **98.0%** | 89.0% |
| Avg Response Tokens | 3,361 | 797 |
| Avg Latency | **1.44s** | 1.57s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- Context7 scores slightly higher on composite for Vitest (4.80 vs 4.77), while Vue Docs MCP leads on API recall (98% vs 89%) and is free to use.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
