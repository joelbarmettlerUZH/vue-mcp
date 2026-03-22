# Tools

Vue Docs MCP exposes tools for each enabled framework. By default, only Vue.js tools are active. See [Framework Preferences](/reference/frameworks) to enable additional frameworks.

## Per-Framework Tools

Each framework registers three tools using the pattern `{framework}_docs_search`, `{framework}_api_lookup`, and `{framework}_get_related`. For Vue.js, the tools are:

- `vue_docs_search`
- `vue_api_lookup`
- `vue_get_related`

If Vue Router is enabled, you also get `vue_router_docs_search`, `vue_router_api_lookup`, and `vue_router_get_related`.

---

## `{framework}_docs_search`

Semantic search across a framework's documentation. This is the primary tool, and the one your AI assistant will use most often.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `string` | Yes | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | No | `"all"` | Documentation section to search |
| `max_results` | `integer` | No | `3` | Number of sections to return (1-20) |

### Scope Values

Use scope to narrow results to a specific part of the docs. Available scopes vary by framework. Read the `{framework}://scopes` resource for the full list.

**Vue.js scopes:**

| Scope | What it searches |
|---|---|
| `all` | Entire Vue.js documentation |
| `guide` | The full guide |
| `guide/essentials` | Guide essentials (reactivity, computed, etc.) |
| `guide/components` | Component-specific guide sections |
| `api` | API reference pages |
| `tutorial` | Interactive tutorial content |
| `examples` | Example gallery |

### Example Queries

- `"how does computed caching work"`
- `"v-model on custom components"`
- `"defineProps TypeScript usage"`
- `"transition group animations"`
- `"provide inject vs props"`

### How It Works

Each search runs a 6-step pipeline:

1. **Embed & detect entities.** Query is embedded via Jina, BM25 sparse vector generated locally, API names detected deterministically.
2. **Hybrid search.** Dense + BM25 search in Qdrant, retrieving up to 50 candidates.
3. **Resolve HyPE hits.** Synthetic question chunks mapped back to parent content.
4. **Cross-reference expansion.** Related documentation sections pulled in from metadata links.
5. **Reranking.** Jina reranker reorders candidates for precision.
6. **Reconstruction.** Results reassembled in documentation reading order.

No LLM is used at query time. Only embedding and reranking API calls are made.

### Response

Returns reconstructed documentation fragments as readable markdown. Results are ordered by their position in the documentation (by reading order, not by score), so they read naturally.

---

## `{framework}_api_lookup`

Instant lookup for any API. Bypasses the full search pipeline for fast, exact results.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `api_name` | `string` | Yes | API name to look up |

### Example API Names (Vue.js)

- `ref`, `reactive`, `computed`, `watch`, `watchEffect`
- `defineProps`, `defineEmits`, `defineExpose`, `defineModel`
- `v-model`, `v-if`, `v-for`, `v-show`, `v-bind`
- `onMounted`, `onUpdated`, `onUnmounted`
- `Transition`, `KeepAlive`, `Teleport`, `Suspense`
- `createApp`, `nextTick`, `toRefs`, `toRaw`

### Response

Returns the API entity's type, documentation page, section, and a table of related APIs. If no exact match is found, falls back to fuzzy matching with typo tolerance.

---

## `{framework}_get_related`

Discover related APIs, concepts, and documentation pages for a given topic.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `topic` | `string` | Yes | API name, concept, or topic |

### Example Topics

- `"ref"`: Related reactivity APIs
- `"reactivity"`: All reactivity-related APIs
- `"component lifecycle"`: Lifecycle hooks and related APIs
- `"Transition"`: Transition-related components and directives
- `"two-way binding"`: v-model and related patterns

### Response

Returns a table of related APIs organized by relationship type, with links to their documentation pages.

---

## `ecosystem_search`

Search across all enabled frameworks at once. Only available when two or more frameworks are enabled via [`set_framework_preferences`](/reference/frameworks).

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `string` | Yes | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | No | `"all"` | Documentation section to search |
| `max_results` | `integer` | No | `5` | Number of sections to return (1-20) |

Results are tagged by source framework and ordered by relevance.
