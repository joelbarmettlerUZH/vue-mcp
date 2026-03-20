# Tools

Vue Docs MCP exposes three tools that your AI assistant can call to search and retrieve Vue.js documentation.

## `vue_docs_search`

Semantic search across the full Vue.js documentation. This is the primary tool, and the one your AI assistant will use most often.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `string` | Yes | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | No | `"all"` | Documentation section to search |
| `max_results` | `integer` | No | `3` | Number of sections to return (1-20) |

### Scope Values

Use scope to narrow results to a specific part of the docs:

| Scope | What it searches |
|---|---|
| `all` | Entire Vue.js documentation |
| `guide` | The full guide |
| `guide/essentials` | Guide essentials (reactivity, computed, etc.) |
| `guide/components` | Component-specific guide sections |
| `api` | API reference pages |
| `tutorial` | Interactive tutorial content |
| `examples` | Example gallery |

Use the [`vue://scopes`](/reference/resources#vue-scopes) resource to get the full list of available scopes.

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

## `vue_api_lookup`

Instant lookup for any Vue API. Bypasses the full search pipeline for fast, exact results.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `api_name` | `string` | Yes | Vue API name |

### Example API Names

- `ref`, `reactive`, `computed`, `watch`, `watchEffect`
- `defineProps`, `defineEmits`, `defineExpose`, `defineModel`
- `v-model`, `v-if`, `v-for`, `v-show`, `v-bind`
- `onMounted`, `onUpdated`, `onUnmounted`
- `Transition`, `KeepAlive`, `Teleport`, `Suspense`
- `createApp`, `nextTick`, `toRefs`, `toRaw`

### Response

Returns the API entity's type, documentation page, section, and a table of related APIs. If no exact match is found, falls back to fuzzy matching with typo tolerance.

---

## `vue_get_related`

Discover related APIs, concepts, and documentation pages for a given topic.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `topic` | `string` | Yes | Vue API name, concept, or topic |

### Example Topics

- `"ref"`: Related reactivity APIs
- `"reactivity"`: All reactivity-related APIs
- `"component lifecycle"`: Lifecycle hooks and related APIs
- `"Transition"`: Transition-related components and directives
- `"two-way binding"`: v-model and related patterns

### Response

Returns a table of related APIs organized by relationship type, with links to their documentation pages.
