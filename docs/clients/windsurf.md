# Windsurf

Connect Vue Docs MCP to [Windsurf](https://devin.ai/desktop).

## Setup

Add to your Windsurf MCP configuration file. Open the config file from the Cascade panel (**...** menu > **Open MCP config file** in the MCPs section). See the [Windsurf MCP docs](https://docs.devin.ai/desktop/cascade/mcp) for more info.

```json
{
  "mcpServers": {
    "vue-docs": {
      "serverUrl": "https://mcp.vue-mcp.org/mcp"
    }
  }
}
```

::: warning Note
Windsurf accepts `serverUrl` or `url` for remote servers; `serverUrl` is what its docs use. Windsurf's website and docs now live under Devin Desktop (devin.ai), so older links may redirect there.
:::

## Verify

After saving the config, check that the Vue Docs tools appear in the Cascade tools list.

## Usage

Ask Windsurf about Vue in Cascade:

- "How does `v-model` work on custom components?"
- "What's the difference between `ref` and `reactive`?"
- "Show me Vue transition animations"

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
