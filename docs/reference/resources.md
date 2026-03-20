# Resources

Resources let your AI assistant browse the Vue.js documentation structure directly, without performing a search. They provide raw access to the table of contents, individual pages, and the API index.

::: tip
Resources are read-only and always return the latest indexed version of the documentation.
:::

## `vue://topics`

Full table of contents for the entire Vue.js documentation.

Returns a hierarchical markdown listing of all documentation pages and sections. Use this to understand what's available before searching.

### With a Section Path

`vue://topics/{section}` returns the table of contents for a specific section.

**Examples:**
- `vue://topics/guide`: Guide table of contents
- `vue://topics/guide/essentials`: Essentials section only
- `vue://topics/api`: API reference table of contents

If the section is not found, the response lists all available top-level sections.

---

## `vue://pages/{path}`

Raw markdown content of any documentation page.

**Examples:**
- `vue://pages/guide/essentials/computed`
- `vue://pages/api/reactivity-core`
- `vue://pages/guide/components/props`

Paths use `/` as separator and do not include the `.md` extension.

---

## `vue://api/index`

Complete index of all Vue.js API entities, grouped by type.

Returns a markdown listing with counts for each category:

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

## `vue://api/entities/{name}` {#vue-api-entities}

Detailed information for a specific API entity.

**Examples:**
- `vue://api/entities/ref`
- `vue://api/entities/computed`
- `vue://api/entities/defineProps`

Returns the entity's type, documentation page, section, and related APIs.

---

## `vue://scopes` {#vue-scopes}

List of all valid search scopes for the [`vue_docs_search`](/reference/tools#vue-docs-search) tool.

Returns a table with each scope's path, page count, and description. Use this to discover which scopes are available for narrowing search results.
