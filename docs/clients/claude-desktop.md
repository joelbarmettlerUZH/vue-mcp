# Claude Desktop

Connect Vue Docs MCP to [Claude Desktop](https://claude.com/download).

## Setup

Claude Desktop connects to remote servers through **custom connectors**. Remote connectors are reached from Anthropic's cloud, which works here because the hosted server is public.

### Pro and Max plans

1. Open Claude Desktop and go to **Customize** > **Connectors** (in older versions: **Settings** > **Connectors**)
2. Click **Add**, then **Add custom connector**
3. Enter name: `Vue Docs`
4. Enter URL: `https://mcp.vue-mcp.org/mcp`
5. Click **Add**. No sign-in is needed.

### Team and Enterprise plans

An organization Owner adds the connector under **Organization settings** > **Connectors**. Members then connect to it from their own Connectors settings.

::: tip Plans
Custom connectors are available on Free (limited to one connector), Pro, Max, Team, and Enterprise.
:::

### Alternative: config file with a bridge

Claude Desktop's config file is documented for local (stdio) programs, while remote servers are added as connectors. If you prefer the config file, or cannot use connectors, bridge to the hosted server with the community [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) package (requires Node.js):

```json
{
  "mcpServers": {
    "vue-docs": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.vue-mcp.org/mcp"]
    }
  }
}
```

| Platform | Config file |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Restart Claude Desktop after saving.

## Verify

Open a new chat and click the **+** (or tools) menu in the message box. `Vue Docs` should appear under Connectors with its tools listed. If you used the config file, restart Claude Desktop first.

## Usage

Ask Claude anything about Vue in the chat:

- "How does `v-model` work on custom components?"
- "What lifecycle hooks are available in Vue 3?"
- "Compare `watch` vs `watchEffect`"

Claude will automatically call the MCP tools and include documentation references in its response.

## Self-Hosted Server

For a [self-hosted instance](/guide/self-hosting) using stdio transport:

::: code-group

```json [macOS]
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "vue-docs": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vue-mcp", "vue-docs-server"]
    }
  }
}
```

```json [Windows]
// %APPDATA%\Claude\claude_desktop_config.json
{
  "mcpServers": {
    "vue-docs": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\vue-mcp", "vue-docs-server"]
    }
  }
}
```

:::
