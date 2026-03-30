# Vitest

<span style="color: var(--vp-c-brand-1); font-weight: 600;">Benchmarks pending</span> &middot; Activate with `set_framework_preferences`

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
