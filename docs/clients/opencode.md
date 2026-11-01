# Opencode

Connect Vue Docs MCP to [Opencode](https://opencode.ai/).

## Setup

## Add Vue Docs MCP

**Option 1: Command line**

```bash
opencode mcp add vue-docs --url https://mcp.vue-mcp.org/mcp --global
```

**Option 2: Configuration file**

Add the following to your OpenCode configuration file:

```json
{
  "mcp": {
    "servers": {
      "vue-docs": {
        "type": "remote",
        "url": "https://mcp.vue-mcp.org/mcp"
      }
    }
  }
}
```

See the [OpenCode MCP documentation](https://opencode.ai/docs/mcp-servers) for details.

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
