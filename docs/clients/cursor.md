# Cursor

Connect Vue Docs MCP to [Cursor](https://cursor.com/).

## Setup

### Option A: One-Click Install

Since Cursor 1.0, you can install MCP servers with a single click:

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=vue-docs&config=eyJ1cmwiOiJodHRwczovL21jcC52dWUtbWNwLm9yZy9tY3AifQ%3D%3D)

### Option B: Via Settings UI

1. Open Cursor
2. Go to **Settings** > **Cursor Settings** > **MCP** > **Add new global MCP server**
3. Paste the JSON configuration below

### Option C: Via Config File

Add to your Cursor MCP config file. You can install globally or per-project:

::: code-group

```json [Global (~/.cursor/mcp.json)]
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

```json [Project (.cursor/mcp.json)]
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

:::

::: tip
**Global** is recommended for Vue Docs MCP since you'll want it in all Vue projects. Use **project-level** config if you only want it in specific projects.
:::

## Verify

After adding the server, check the MCP section in Cursor Settings. The `vue-docs` server should show a green status indicator.

## Usage

Ask Cursor about Vue in chat or Composer mode:

- "How does computed caching work?"
- "Show me the defineProps TypeScript API"
- "Help me migrate from Options API to Composition API"

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
