# Windsurf

Connect Vue Docs MCP to [Windsurf](https://windsurf.com/).

## Setup

Add to your Windsurf MCP configuration file. See [Windsurf MCP docs](https://docs.windsurf.com/windsurf/cascade/mcp) for more info.

```json
{
  "mcpServers": {
    "vue-docs": {
      "serverUrl": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

::: warning Note
Windsurf uses `serverUrl` instead of `url`. This differs from most other clients.
:::

## Verify

After saving the config, check that the Vue Docs tools appear in the Cascade tools list.

## Usage

Ask Windsurf about Vue in Cascade:

- "How does `v-model` work on custom components?"
- "What's the difference between `ref` and `reactive`?"
- "Show me Vue transition animations"

## Self-Hosted Server

For a [self-hosted instance](/guide/self-hosting):

```json
{
  "mcpServers": {
    "vue-docs": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vue-mcp", "vue-docs-server"]
    }
  }
}
```
