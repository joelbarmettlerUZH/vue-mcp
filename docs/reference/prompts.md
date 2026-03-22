# Prompts

Prompts are guided workflows that structure how your AI assistant approaches common tasks. Each enabled framework registers its own prompts.

::: info
Prompt support varies by MCP client. Claude Desktop and Claude Code support prompts natively. Other clients may expose them differently or not at all.
:::

## Per-Framework Prompts

Each framework registers three prompts using the pattern `debug_{framework}_issue`, `compare_{framework}_apis`, and `migrate_{framework}_pattern`. For Vue.js, the prompts are:

- `debug_vue_issue`
- `compare_vue_apis`
- `migrate_vue_pattern`

---

## `debug_{framework}_issue`

Systematic debugging workflow for framework-specific issues.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `symptom` | Yes | Description of unexpected behavior or error message |
| `code_snippet` | No | Relevant code where the issue occurs |

### Workflow

Your AI assistant will:

1. Identify the concept involved
2. Search the documentation with `{framework}_docs_search`
3. Look up specific APIs using `{framework}_api_lookup`
4. Explore related patterns with `{framework}_get_related`
5. Explain the root cause with documentation references
6. Provide a fix and prevention tip

### Example

> **Symptom:** "My computed property isn't updating when I push to an array"
>
> The assistant would search for computed reactivity caveats, look up `computed` and `reactive`, and explain Vue's reactivity tracking for array mutations.

---

## `compare_{framework}_apis`

Side-by-side comparison of APIs or patterns within a framework.

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

### Example Comparisons (Vue.js)

- `"ref, reactive"`: When to use which reactivity primitive
- `"computed, watch"`: Derived state vs side effects
- `"v-if, v-show"`: Conditional rendering strategies
- `"props, provide/inject"`: Data passing patterns
- `"Options API, Composition API"`: API style comparison

---

## `migrate_{framework}_pattern`

Step-by-step migration guide between patterns within a framework.

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

### Example Migrations (Vue.js)

- `"Options API"` -> `"Composition API"`
- `"Vue 2 mixins"` -> `"composables"`
- `"event bus"` -> `"provide/inject"`
- `"Vuex"` -> `"Pinia"`
- `"Vue 2 filters"` -> `"computed properties"`
