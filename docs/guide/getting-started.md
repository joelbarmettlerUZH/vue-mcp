# Getting Started

The fastest way to start using Vue Docs MCP is to connect to the free hosted server at **`mcp.vue-mcp.org`**. No API keys or setup required.

## Connect Your Client

### Claude Code

One command:

```bash
claude mcp add --scope user vue-docs --transport streamable-http https://mcp.vue-mcp.org/mcp
```

### Cursor

One-click install:

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=vue-docs&config=eyJ1cmwiOiJodHRwczovL21jcC52dWUtbWNwLm9yZy9tY3AifQ%3D%3D)

Or add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

### Other Clients

See the [MCP Clients](/clients/) section for detailed setup instructions for Claude Desktop, Windsurf, VS Code, JetBrains, Zed, ChatGPT, and more.

For any client not listed, use the streamable HTTP transport with this URL:

```
https://mcp.vue-mcp.org/mcp
```

## Try It Out

Once connected, ask your AI assistant a Vue question. It will use the MCP tools automatically:

- "How does `v-model` work on custom components?"
- "What lifecycle hooks are available in Vue 3?"
- "Show me the `defineProps` API"
- "Compare `watch` vs `watchEffect`"

Look for tool calls like `vue_docs_search` or `vue_api_lookup` in the response.

## What's Available

| Type | What it does |
|---|---|
| [**Tools**](/reference/tools) | Search docs, look up APIs, find related content |
| [**Resources**](/reference/resources) | Browse the documentation tree, read raw pages |
| [**Prompts**](/reference/prompts) | Guided workflows for debugging, comparison, migration |

## Next Steps

- [MCP Clients](/clients/): Setup guides for all supported clients
- [Tools Reference](/reference/tools): Full documentation of search tools
- [How It Works](/reference/how-it-works): Technical details of the search pipeline
- [Self-Hosting](/guide/self-hosting): Run your own instance
