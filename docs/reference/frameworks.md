# Framework Preferences

Vue Docs MCP supports multiple frameworks in the Vue ecosystem. Each framework gets its own tools, resources, and prompts. You can control which frameworks are active in your session.

## Default Configuration

By default, only **Vue.js** is enabled. If your project uses additional frameworks like Vue Router, you need to activate them.

## `set_framework_preferences`

Call this tool to enable or disable frameworks for the current session.

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `vue` | `boolean` | `true` | Enable Vue.js core documentation |
| `vue_router` | `boolean` | `false` | Enable Vue Router documentation |

### Example

To work on a project that uses both Vue and Vue Router:

```
set_framework_preferences(vue=true, vue_router=true)
```

After calling this, your AI assistant will have access to tools, resources, and prompts for both frameworks.

### Effect

When a framework is enabled, the following become available:

- **Tools**: `{framework}_docs_search`, `{framework}_api_lookup`, `{framework}_get_related`
- **Resources**: `{framework}://topics`, `{framework}://pages/{path}`, `{framework}://api/index`, etc.
- **Prompts**: `debug_{framework}_issue`, `compare_{framework}_apis`, `migrate_{framework}_pattern`

When more than one framework is enabled, an additional `ecosystem_search` tool becomes available that searches across all active frameworks at once.

## `ecosystem_search`

Searches across all enabled frameworks simultaneously. Results are tagged by source framework and ordered by relevance.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `string` | Yes | | Developer question or topic (max 2000 chars) |
| `scope` | `string` | No | `"all"` | Documentation section to search |
| `max_results` | `integer` | No | `5` | Number of sections to return (1-20) |

This tool is only available when two or more frameworks are enabled.

## Checking Current Preferences

Read the `ecosystem://preferences` resource to see which frameworks are currently active and what tools are available.

Read `ecosystem://sources` to see all supported frameworks and their status.

## Available Frameworks

See the [Supported Frameworks](/frameworks/) page for the full list of available and planned frameworks, including per-framework tools, benchmarks, and documentation.
