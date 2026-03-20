# VS Code (Copilot)

Connect Vue Docs MCP to [VS Code](https://code.visualstudio.com/) with GitHub Copilot.

## Setup

Add to your VS Code MCP config file (`.vscode/mcp.json`). See [VS Code MCP docs](https://code.visualstudio.com/docs/copilot/chat/mcp-servers) for more info.

```json
{
  "servers": {
    "vue-docs": {
      "type": "http",
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

::: tip
VS Code uses `servers` (not `mcpServers`) and requires a `type` field.
:::

## Verify

After saving, open the Copilot Chat panel. The Vue Docs tools should appear in the available tools list.

## Usage

Ask Copilot about Vue in the chat panel:

- "How does computed caching work in Vue 3?"
- "Show me the `defineEmits` API"
- "Help me set up `provide`/`inject`"

## Copilot Coding Agent

For the [Copilot Coding Agent](https://docs.github.com/en/copilot/how-tos/agents/copilot-coding-agent/extending-copilot-coding-agent-with-mcp), add to your repository settings under **Settings > Copilot > Coding agent > MCP configuration**:

```json
{
  "mcpServers": {
    "vue-docs": {
      "type": "http",
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

## Visual Studio 2022

For [Visual Studio 2022](https://learn.microsoft.com/visualstudio/ide/mcp-servers):

```json
{
  "servers": {
    "vue-docs": {
      "type": "http",
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

## Self-Hosted Server

For a [self-hosted instance](/guide/self-hosting):

```json
{
  "servers": {
    "vue-docs": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vue-mcp", "vue-docs-server"]
    }
  }
}
```
