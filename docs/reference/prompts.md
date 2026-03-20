# Prompts

Prompts are guided workflows that structure how your AI assistant approaches common Vue.js tasks. They combine multiple tool calls into a coherent sequence.

::: info
Prompt support varies by MCP client. Claude Desktop and Claude Code support prompts natively. Other clients may expose them differently or not at all.
:::

## `debug_vue_issue`

Systematic debugging workflow for Vue.js issues.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `symptom` | Yes | Description of unexpected behavior or error message |
| `code_snippet` | No | Relevant code where the issue occurs |

### Workflow

Your AI assistant will:

1. Identify the Vue concept involved
2. Search the documentation with `vue_docs_search`
3. Look up specific APIs using `vue_api_lookup`
4. Explore related patterns with `vue_get_related`
5. Explain the root cause with documentation references
6. Provide a fix and prevention tip

### Example

> **Symptom:** "My computed property isn't updating when I push to an array"
>
> The assistant would search for computed reactivity caveats, look up `computed` and `reactive`, and explain Vue's reactivity tracking for array mutations.

---

## `compare_vue_apis`

Side-by-side comparison of Vue APIs or patterns.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `items` | Yes | Comma-separated list of APIs or patterns to compare |

### Output

A structured comparison including:

- Purpose and use case for each item
- Reactivity behavior differences
- Performance characteristics
- "Use when..." decision criteria
- Code examples showing key differences
- Common mistakes

### Example Comparisons

- `"ref, reactive"`: When to use which reactivity primitive
- `"computed, watch"`: Derived state vs side effects
- `"v-if, v-show"`: Conditional rendering strategies
- `"props, provide/inject"`: Data passing patterns
- `"Options API, Composition API"`: API style comparison

---

## `migrate_vue_pattern`

Step-by-step migration guide between Vue patterns.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `from_pattern` | Yes | Current pattern or API style |
| `to_pattern` | Yes | Target pattern or API style |

### Output

1. **Why migrate.** Benefits of the target pattern.
2. **Concept mapping.** Table mapping old concepts to new equivalents.
3. **Step-by-step migration.** Before/after code examples.
4. **Common gotchas.** Pitfalls to watch for during migration.

### Example Migrations

- `"Options API"` -> `"Composition API"`
- `"Vue 2 mixins"` -> `"composables"`
- `"event bus"` -> `"provide/inject"`
- `"Vuex"` -> `"Pinia"`
- `"Vue 2 filters"` -> `"computed properties"`
