# VitePress

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.58 / 5 composite score</span> &middot; 100.0% API recall &middot; 45 questions evaluated

Vue Docs MCP provides deep access to the official [VitePress documentation](https://vitepress.dev), covering the static site generator's runtime API (composables, helpers, components), default theme config, build hooks, data loaders, deploy guides, and migration paths from VuePress.

::: tip Dogfood
This very documentation site is built with VitePress, so the MCP can answer questions about the tool you're reading right now.
:::

## Activation

VitePress is not enabled by default. Call `set_framework_preferences` to activate it:

```
set_framework_preferences(vitepress=true)
```

## Tools

### `vitepress_docs_search`

Semantic search over VitePress documentation. Uses the standard 6-step retrieval pipeline: embed query, hybrid search (dense + BM25), resolve HyPE hits, expand cross-references, rerank, and reconstruct into readable markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `reference`

### `vitepress_api_lookup`

Fast exact-match API reference lookup with fuzzy fallback. Returns type signatures, descriptions, and usage examples directly from the documentation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_name` | `string` | | API name to look up (e.g. `useData`, `defineConfig`, `createContentLoader`, `withBase`) |

### `vitepress_get_related`

Find related APIs, concepts, and documentation pages for a given API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `topic` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vitepress://topics` | Full table of contents |
| `vitepress://topics/{section}` | TOC for a specific section (e.g. `vitepress://topics/reference`) |
| `vitepress://pages/{path}` | Raw markdown of any doc page (e.g. `vitepress://pages/reference/site-config`) |
| `vitepress://api/index` | Complete API entity index grouped by type |
| `vitepress://api/entities/{name}` | Details for a specific API (e.g. `vitepress://api/entities/useData`) |
| `vitepress://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vitepress_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging workflow: identifies the concept, searches docs, looks up APIs, and provides a fix |
| `compare_vitepress_apis` | `items` (comma-separated) | Side-by-side comparison of APIs or patterns (e.g. `createContentLoader, defineLoader`) |
| `migrate_vitepress_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns (e.g. VuePress to VitePress) |

## Coverage

| Area | What's indexed |
|---|---|
| Runtime API | `useData`, `useRoute`, `useRouter`, `withBase`, `<Content>`, `<ClientOnly>`, template globals |
| Site config | All top-level keys: `title`, `head`, `cleanUrls`, `rewrites`, `srcDir`, `outDir`, `markdown`, build hooks |
| Default theme | Sidebar, nav, search, social links, footer, edit link, last updated, outline, aside, dark mode |
| Theme components | `VPTeamMembers`, `VPTeamPage`, hero/features layouts |
| Data loaders | `createContentLoader`, `defineLoader`, dynamic routes |
| Guides | Getting started, deploy, i18n, SSR compatibility, asset handling, custom themes |
| CLI | `vitepress dev`, `vitepress build`, `vitepress preview`, `vitepress init` |
| Migration | From VuePress, from VitePress 0.x |

## Benchmarks vs Context7

Evaluated on 50 VitePress questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.80, 4.71, 4.76, 3.67, 4.96] },
    { name: 'Context7', data: [4.76, 4.69, 4.71, 4.20, 4.73] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.80** | 4.76 |
| Completeness | **4.71** | 4.69 |
| Correctness | **4.76** | 4.71 |
| API Coverage | 3.67 | **4.20** |
| Conciseness | **4.96** | 4.73 |
| **Composite** | 4.58 | **4.62** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | 95.6% | 95.6% |
| API Recall | 100.0% | 100.0% |
| Avg Response Tokens | 3,056 | **779** |
| Avg Latency | **0.83s** | 1.78s |
| P95 Latency | **1.03s** | 2.15s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes on Fairness

- Context7 is a general-purpose service covering 9000+ libraries. Vue Docs MCP is purpose-built for the Vue ecosystem.
- The evaluation framework is open source in the `eval/` directory. Run `make eval-compare` to reproduce.
