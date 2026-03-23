# Resources

Resources let your AI assistant browse documentation structure directly, without performing a search. They provide raw access to the table of contents, individual pages, and the API index.

::: tip
Resources are read-only and always return the latest indexed version of the documentation.
:::

## Per-Framework Resources

Each enabled framework registers resources using the `{framework}://` URI scheme.

| URI Pattern | Description |
|---|---|
| `{framework}://topics` | Full table of contents |
| `{framework}://topics/{section}` | TOC for a specific section |
| `{framework}://pages/{path}` | Raw markdown of any documentation page |
| `{framework}://api/index` | Complete API entity index grouped by type |
| `{framework}://api/entities/{name}` | Details for a specific API entity |
| `{framework}://scopes` | Valid search scope values for `{framework}_docs_search` |

Paths use `/` as separator and do not include the `.md` extension. Every indexed page and API entity is enumerated as a concrete resource, so your AI assistant can discover and browse them directly.

See the framework pages for concrete URIs and examples:
- [Vue.js resources](/frameworks/vue#resources)
- [Vue Router resources](/frameworks/vue-router#resources)

## Ecosystem Resources

These resources are always available regardless of which frameworks are enabled.

| URI | Description |
|---|---|
| `ecosystem://preferences` | Current framework activation settings and available tools |
| `ecosystem://sources` | All supported frameworks with their documentation URLs and status |
