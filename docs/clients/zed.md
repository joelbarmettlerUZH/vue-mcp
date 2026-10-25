# Zed

Connect Vue Docs MCP to [Zed](https://zed.dev/).

## Setup

Add to your Zed `settings.json`. See the [Zed MCP docs](https://zed.dev/docs/ai/mcp) for more info.

```json
{
  "context_servers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

Or use the UI: **Settings** > **AI** > **MCP Servers** > **Add Server** > **Add Remote Server**.

::: tip
Zed uses `context_servers` instead of `mcpServers`.
:::

## Verify

After saving, the Vue Docs tools should be available in Zed's assistant panel.

## Usage

Ask the assistant about Vue:

- "How does reactivity work in Vue 3?"
- "Show me the `Teleport` component API"
- "Help me with component `props` validation"
