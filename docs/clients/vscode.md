# VS Code (Copilot)

Connect Vue Docs MCP to [VS Code](https://code.visualstudio.com/) with GitHub Copilot.

## Setup

Add to your VS Code MCP config file (`.vscode/mcp.json`). See [VS Code MCP docs](https://code.visualstudio.com/docs/agent-customization/mcp-servers) for more info.

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
VS Code uses `servers` (not `mcpServers`) and requires a `type` field. `http` is streamable HTTP; the `sse` type is the older transport, which this server does not offer.

You can also run **MCP: Add Server** > **HTTP** from the Command Palette, or from a terminal:

```bash
code --add-mcp '{"name":"vue-docs","type":"http","url":"https://mcp.vue-mcp.org/mcp"}'
```
:::

## Verify

After saving, open the Copilot Chat panel. The Vue Docs tools should appear in the available tools list.

## Usage

Ask Copilot about Vue in the chat panel:

- "How does computed caching work in Vue 3?"
- "Show me the `defineEmits` API"
- "Help me set up `provide`/`inject`"

## Copilot Coding Agent

For the [Copilot Coding Agent](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/configure-mcp-servers), add to your repository settings under **Settings > Copilot > Coding agent > MCP configuration**:

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

For [Visual Studio 2022](https://learn.microsoft.com/en-us/visualstudio/ide/mcp-servers):

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
