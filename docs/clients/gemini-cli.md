# Gemini CLI

Connect Vue Docs MCP to [Gemini CLI](https://google-gemini.github.io/gemini-cli/).

## Setup

Open the Gemini CLI settings file at `~/.gemini/settings.json` and add:

```json
{
  "mcpServers": {
    "vue-docs": {
      "httpUrl": "https://mcp.vue-mcp.org/mcp",
      "headers": {
        "Accept": "application/json, text/event-stream"
      }
    }
  }
}
```

::: warning Note
Gemini CLI uses `httpUrl` instead of `url`, and requires the `Accept` header for streamable HTTP connections.
:::

## Verify

After saving, restart Gemini CLI. The Vue Docs tools should be available.

## Usage

Ask Gemini about Vue:

- "How does `v-model` work on custom components?"
- "Show me the reactivity API reference"
- "Help me migrate from mixins to composables"

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
