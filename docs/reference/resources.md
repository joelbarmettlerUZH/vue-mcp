# Resources

Resources let your AI assistant browse documentation structure directly, without performing a search. They provide raw access to the table of contents, individual pages, and the API index.

::: tip
Resources are read-only and always return the latest indexed version of the documentation.
:::

## Per-Framework Resources

Each enabled framework registers its own set of resources using the `{framework}://` URI scheme. For Vue.js, the prefix is `vue://`. If Vue Router is enabled, its resources use `vue-router://`.

See [Framework Preferences](/reference/frameworks) to enable additional frameworks.

---

## `{framework}://topics`

Full table of contents for the framework's documentation.

Returns a hierarchical markdown listing of all documentation pages and sections. Use this to understand what's available before searching.

### With a Section Path

`{framework}://topics/{section}` returns the table of contents for a specific section.

**Examples (Vue.js):**
- `vue://topics/guide`: Guide table of contents
- `vue://topics/guide/essentials`: Essentials section only
- `vue://topics/api`: API reference table of contents

If the section is not found, the response lists all available top-level sections.

---

## `{framework}://pages/{path}`

Raw markdown content of any documentation page.

**Examples (Vue.js):**
- `vue://pages/guide/essentials/computed`
- `vue://pages/api/reactivity-core`
- `vue://pages/guide/components/props`

Paths use `/` as separator and do not include the `.md` extension. Every indexed page is enumerated as a concrete resource, so your AI assistant can browse them directly.

---

## `{framework}://api/index`

Complete index of all API entities for the framework, grouped by type.

Returns a markdown listing with counts for each category. For Vue.js, this includes:

- Lifecycle Hooks
- Composables
- Directives
- Components
- Compiler Macros
- Global APIs
- Options
- Instance Methods
- Instance Properties

---

## `{framework}://api/entities/{name}` {#api-entities}

Detailed information for a specific API entity.

**Examples (Vue.js):**
- `vue://api/entities/ref`
- `vue://api/entities/computed`
- `vue://api/entities/defineProps`

Returns the entity's type, documentation page, section, and related APIs. Every known API entity is enumerated as a concrete resource.

---

## `{framework}://scopes` {#scopes}

List of all valid search scopes for the `{framework}_docs_search` tool.

Returns a table with each scope's path, page count, and description. Use this to discover which scopes are available for narrowing search results.

---

## Ecosystem Resources

These resources are always available regardless of which frameworks are enabled.

### `ecosystem://preferences`

Shows which frameworks are currently enabled and what tools, resources, and prompts are available in the session.

### `ecosystem://sources`

Lists all supported frameworks with their name, documentation URL, and whether they are currently enabled.
