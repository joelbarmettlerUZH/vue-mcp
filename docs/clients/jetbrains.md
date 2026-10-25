# JetBrains IDEs

Connect Vue Docs MCP to any [JetBrains IDE](https://www.jetbrains.com/) (WebStorm, IntelliJ IDEA, PyCharm, etc.) with AI Assistant.

## Setup

See the [JetBrains AI Assistant MCP docs](https://www.jetbrains.com/help/ai-assistant/mcp.html) for full details.

### Via Settings UI

1. Go to **Settings** > **Tools** > **AI Assistant** > **Model Context Protocol (MCP)**
2. Click **+ Add**
3. Select the **HTTP** tab
4. Paste the configuration:

```json
{
  "mcpServers": {
    "vue-docs": {
      "url": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

5. Click **Apply**

::: tip
Use the base endpoint `https://mcp.vue-mcp.org/mcp` (streamable HTTP). JetBrains also supports legacy SSE servers, whose URLs end in `/sse`; this server does not offer that endpoint.
:::

### Via Config File

Alternatively, add the JSON above directly to your MCP config file.

## Verify

After applying, the Vue Docs tools should appear in the AI Assistant MCP tools list.

## Usage

Ask AI Assistant about Vue:

- "How does `v-model` work with custom components?"
- "Show me the `computed` API reference"
- "Compare `ref` and `reactive`"

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
