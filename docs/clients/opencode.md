# Opencode

Connect Vue Docs MCP to [Opencode](https://opencode.ai/).

## Setup

Add to your Opencode configuration file. See the [Opencode MCP docs](https://opencode.ai/docs/mcp-servers) for more info.

```json
{
  "mcp": {
    "vue-docs": {
      "type": "remote",
      "url": "https://mcp.vue-mcp.org/mcp",
      "enabled": true
    }
  }
}
```

## Verify

After saving, the Vue Docs tools should appear in the available tools list.

## Usage

Ask about Vue:

- "How does computed caching work?"
- "Show me the `defineProps` API"
- "Compare `watch` vs `watchEffect`"

## Self-Hosted Server

For a [self-hosted instance](/guide/self-hosting):

```json
{
  "mcp": {
    "vue-docs": {
      "type": "local",
      "command": ["uv", "run", "--directory", "/path/to/vue-mcp", "vue-docs-server"],
      "enabled": true
    }
  }
}
```
