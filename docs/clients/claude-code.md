# Claude Code

Connect Vue Docs MCP to [Claude Code](https://code.claude.com/docs) with a single command.

## Setup

Run this in your terminal:

```bash
claude mcp add --scope user vue-docs --transport http https://mcp.vue-mcp.org/mcp
```

That's it. Claude Code will now use Vue documentation tools automatically when you ask Vue-related questions.

### Verify

Check that the server is connected:

```bash
claude mcp list
```

You should see `vue-docs` in the list.

### Share with your team

To check the server into a repository, add it to `.mcp.json` at the project root, or use `--scope project`:

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

::: warning Note
Keep the `"type": "http"` field. Claude Code treats an entry with a `url` but no `type` as a misconfigured local server and skips it. The `sse` transport is deprecated, and this server does not offer it.
:::

### Remove

```bash
claude mcp remove vue-docs
```

## Scope Options

| Flag | Effect |
|---|---|
| `--scope user` | Available in all projects (recommended) |
| `--scope project` | Only available in the current project |

## Usage

Just ask Claude anything about Vue. It will call the MCP tools automatically:

```
> How does computed caching work in Vue 3?
> What's the difference between ref and reactive?
> Show me the defineProps API
```

You can also be explicit:

```
> Use docs_search to find documentation about Transition animations
> Look up the onMounted lifecycle hook using api_lookup
```

## Self-Hosted Server

If you're running your own instance with [stdio transport](/guide/self-hosting):

```bash
claude mcp add --scope user vue-docs -- uv run --directory /path/to/vue-mcp vue-docs-server
```
