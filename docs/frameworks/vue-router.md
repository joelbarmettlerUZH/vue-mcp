# Vue Router

<span style="color: var(--vp-c-brand-1); font-weight: 600;">4.78 / 5 composite score</span> &middot; 88.8% API recall &middot; 49 questions evaluated

Vue Docs MCP provides deep access to the official [Vue Router documentation](https://router.vuejs.org), covering route configuration, navigation guards, dynamic routing, lazy loading, data loaders, file-based routing, and the full API reference.

## Activation

Vue Router is not enabled by default. Activate it with:

```
set_framework_preferences(vue_router=true)
```

## Tools

### `vue_router_docs_search`

Semantic search over Vue Router documentation. Covers guide pages, data loaders, file-based routing, migration guides, and API reference.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search within |
| `max_results` | `integer` | `3` | Number of sections to return (1-20) |

**Scope values:** `all`, `guide`, `guide/essentials`, `guide/advanced`, `guide/migration`, `data-loaders`, `file-based-routing`

### `vue_router_api_lookup`

Fast exact-match API reference lookup for Vue Router APIs.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name to look up (e.g. `useRouter`, `createRouter`, `beforeEach`) |

**Example API names:** `useRouter`, `useRoute`, `useLink`, `createRouter`, `createWebHistory`, `createWebHashHistory`, `createMemoryHistory`, `RouterLink`, `RouterView`, `beforeEach`, `beforeResolve`, `afterEach`, `onBeforeRouteLeave`, `onBeforeRouteUpdate`, `scrollBehavior`

### `vue_router_get_related`

Find related APIs, concepts, and documentation pages for a given Vue Router API or topic.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | | API name or concept to explore |

## Resources

| URI | Description |
|---|---|
| `vue-router://topics` | Full table of contents |
| `vue-router://topics/{section}` | TOC for a specific section (e.g. `vue-router://topics/guide/advanced`) |
| `vue-router://pages/{path}` | Raw markdown of any doc page (e.g. `vue-router://pages/guide/essentials/navigation`) |
| `vue-router://api/index` | Complete API entity index grouped by type |
| `vue-router://api/entities/{name}` | Details for a specific API (e.g. `vue-router://api/entities/useRouter`) |
| `vue-router://scopes` | All valid search scope values |

## Prompts

| Prompt | Parameters | Description |
|---|---|---|
| `debug_vue_router_issue` | `symptom`, `code_snippet` (optional) | Systematic debugging for routing issues: navigation failures, guard problems, params not updating |
| `compare_vue_router_apis` | `items` (comma-separated) | Side-by-side comparison (e.g. `router.push, router.replace` or `beforeEach, beforeEnter`) |
| `migrate_vue_router_pattern` | `from_pattern`, `to_pattern` | Migration guide (e.g. Vue Router 3 to 4, Options API guards to Composition API) |

## Benchmarks vs Context7

Evaluated on 49 Vue Router questions scored by an LLM judge (Gemini, temperature 0) across 5 dimensions on a 1-5 scale.

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
    { name: 'Vue Docs MCP', data: [4.94, 4.78, 4.86, 4.43, 4.92] },
    { name: 'Context7', data: [3.53, 3.04, 3.18, 2.33, 4.59] },
  ]"
/>
</ClientOnly>

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Relevance | **4.94** | 3.53 |
| Completeness | **4.78** | 3.04 |
| Correctness | **4.86** | 3.18 |
| API Coverage | **4.43** | 2.33 |
| Conciseness | 4.92 | 4.59 |
| **Composite** | **4.78** | **3.33** |

### Retrieval and Cost

| Metric | Vue Docs MCP | Context7 |
|---|---|---|
| Path Recall | **95.9%** | 42.9% |
| API Recall | **88.8%** | 34.4% |
| Avg Latency | 2.76s | **1.83s** |
| Cost per Query (user-facing) | **Free** | $0.002 |

### Notes

- Context7 performs notably better on Vue Router (3.33 composite) than on Vue.js core (2.41), suggesting their Vue Router documentation coverage is stronger.
- Our API recall (88.8%) is slightly lower than Vue.js (98.7%) because Vue Router's TypeDoc-generated API docs are not yet included in ingestion (they require a build step). This will improve once TypeDoc generation is integrated.
- The evaluation framework is open source in the `eval/` directory.
