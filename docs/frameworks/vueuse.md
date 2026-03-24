# VueUse

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.89 / 5 composite score</span> &middot; 100% API recall &middot; 50 questions evaluated

Vue Docs MCP provides deep access to the official [VueUse documentation](https://vueuse.org), covering 200+ composable utility functions for the Vue Composition API, including state management, browser APIs, sensors, network, animation, and more.

## Activation

VueUse is not enabled by default. Activate it with:

```
set_framework_preferences(vueuse=true)
```

## Tools

### `vueuse_docs_search`

Semantic search over VueUse documentation. Covers guide pages and all composable function docs across `@vueuse/core`, `@vueuse/shared`, `@vueuse/integrations`, `@vueuse/math`, and more.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `core`, `shared`, `integrations`, `math`, `router`

### `vueuse_api_lookup`

Fast exact-match API reference lookup for VueUse composables.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `useMouse`, `useStorage`, `useFetch`) |

**Example API names:** `useMouse`, `useStorage`, `useLocalStorage`, `useFetch`, `useDark`, `useColorMode`, `useBreakpoints`, `useClipboard`, `useDebounceFn`, `useThrottleFn`, `useIntersectionObserver`, `useEventListener`, `useMagicKeys`, `useVModel`, `useWindowSize`, `useFullscreen`, `useWebSocket`, `useAsyncState`, `useRefHistory`

### `vueuse_get_related`

Find related APIs, concepts, and documentation pages for a given VueUse composable or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vueuse://topics` | Full table of contents |
| `vueuse://topics/{section}` | TOC for a specific section (e.g. `vueuse://topics/core`) |
| `vueuse://pages/{path}` | Raw markdown of any doc page (e.g. `vueuse://pages/core/useMouse/index`) |
| `vueuse://api/index` | Complete API entity index grouped by type |
| `vueuse://api/entities/{name}` | Details for a specific API (e.g. `vueuse://api/entities/useMouse`) |
| `vueuse://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vueuse_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging for composable issues: reactivity problems, SSR compatibility, lifecycle timing |
| `compare_vueuse_apis` | `items` (comma-separated) | Side-by-side comparison (e.g. `useStorage, useLocalStorage` or `useDebounceFn, useThrottleFn`) |
| `migrate_vueuse_pattern` | `from_pattern`, `to_pattern` | Migration guide between patterns or VueUse versions |

## Benchmarks

Evaluated on 50 VueUse questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [5.00, 4.88, 4.94, 4.86, 4.78] },
    { name: 'Context7', data: [4.04, 3.54, 3.68, 4.10, 4.82] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **5.00** | 4.04 |
| Completeness | **4.88** | 3.54 |
| Correctness | **4.94** | 3.68 |
| API Coverage | **4.86** | 4.10 |
| Conciseness | 4.78 | 4.82 |
| **Composite** | **4.89** | **4.04** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **97.0%** | 85.0% |
| API Recall | **100.0%** | 92.0% |
| Avg Latency | **0.78s** | 1.84s |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes

- VueUse achieves the highest composite score (4.89) across all three supported frameworks, with perfect 100% API recall.
- Context7 performs notably better on VueUse (4.04 composite) than on Vue.js (2.41) or Vue Router (3.33), likely because VueUse's per-function documentation structure is clean and self-contained.
- The evaluation framework is open source in the `eval/` directory.
