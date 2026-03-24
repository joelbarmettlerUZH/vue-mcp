# VueUse

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
