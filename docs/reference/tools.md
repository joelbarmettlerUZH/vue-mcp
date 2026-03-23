# Tools

Vue Docs MCP exposes tools for each enabled framework. Each framework page documents its specific tools, parameters, and scope values in detail.

## Per-Framework Tools

Every framework registers three tools:

| Tool Pattern | Purpose |
|---|---|
| `{framework}_docs_search` | Semantic search over the framework's documentation |
| `{framework}_api_lookup` | Instant API reference lookup with fuzzy fallback |
| `{framework}_get_related` | Discover related APIs, concepts, and documentation pages |

See the framework pages for concrete tool names, parameters, and examples:
- [Vue.js tools](/frameworks/vue#tools)
- [Vue Router tools](/frameworks/vue-router#tools)

## How Search Works

Each `{framework}_docs_search` call runs a 6-step pipeline:

1. **Embed & detect entities.** Query is embedded via Jina, BM25 sparse vector generated locally, API names detected deterministically.
2. **Hybrid search.** Dense + BM25 search in Qdrant, retrieving up to 50 candidates.
3. **Resolve HyPE hits.** Synthetic question chunks mapped back to parent content.
4. **Cross-reference expansion.** Related documentation sections pulled in from metadata links.
5. **Reranking.** Jina reranker reorders candidates for precision.
6. **Reconstruction.** Results reassembled in documentation reading order.

No LLM is used at query time. Only embedding and reranking API calls are made.

## Cross-Framework Search

When two or more frameworks are enabled, an `ecosystem_search` tool becomes available that searches across all active frameworks simultaneously.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | `"all"` | Documentation section to search |
| `max_results` | `integer` | `5` | Number of sections to return (1-20) |

Results are tagged by source framework and ordered by relevance. Enable frameworks via [`set_framework_preferences`](/frameworks/#activating-frameworks).
