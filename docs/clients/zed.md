# Zed

Connect Vue Docs MCP to [Zed](https://zed.dev/).

## Setup

Add to your Zed `settings.json`. See the [Zed Context Server docs](https://zed.dev/docs/assistant/context-servers) for more info.

```json
{
  "context_servers": {
    "vue-docs": {
      "source": "custom",
      "settings": {
        "url": "https://mcp.vue-mcp.org/mcp"
      }
    }
  }
}
```

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
