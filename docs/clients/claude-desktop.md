# Claude Desktop

Connect Vue Docs MCP to [Claude Desktop](https://claude.ai/download).

## Setup

### Option A: Via Settings UI

1. Open Claude Desktop
2. Go to **Settings** > **Connectors** > **Add Custom Connector**
3. Enter name: `Vue Docs`
4. Enter URL: `https://mcp.vue-mcp.org/mcp`
5. Click **Save**

### Option B: Via Config File

Edit the Claude Desktop configuration file for your platform:

::: code-group

```json [macOS]
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

```json [Windows]
// %APPDATA%\Claude\claude_desktop_config.json
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

```json [Linux]
// ~/.config/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

:::

Restart Claude Desktop after saving.

## Verify

After restarting, you should see a tools icon in the chat input area. Click it to confirm `vue-docs` tools are listed.

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
