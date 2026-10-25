# MCP Clients

Vue Docs MCP works with any client that supports the [Model Context Protocol](https://modelcontextprotocol.io/). The hosted server is free and requires no API key.

::: tip Quickest Setup
Most clients just need this URL:
```
https://mcp.vue-mcp.org/mcp
```
:::

## Dedicated Guides

Detailed setup instructions for popular clients:

| Client | Type | Guide |
|---|---|---|
| [Claude Code](/clients/claude-code) | CLI | One command setup |
| [Claude Desktop](/clients/claude-desktop) | Desktop app | Custom connector |
| [Cursor](/clients/cursor) | IDE | One-click or JSON config |
| [Windsurf](/clients/windsurf) | IDE | JSON config |
| [VS Code (Copilot)](/clients/vscode) | IDE | JSON config |
| [JetBrains](/clients/jetbrains) | IDE | UI or JSON config |
| [Zed](/clients/zed) | IDE | JSON config |
| [Opencode](/clients/opencode) | CLI | JSON config |
| [Gemini CLI](/clients/gemini-cli) | CLI | JSON config |
| [ChatGPT](/clients/chatgpt) | Web/Desktop | App connector |

## Other Clients

For any MCP client not listed above, use the **streamable HTTP** transport with this URL:

```
https://mcp.vue-mcp.org/mcp
```

No authentication headers are needed. Consult your client's MCP documentation for configuration details.

::: warning SSE is not supported
The older HTTP+SSE transport (endpoints ending in `/sse`) is deprecated, and the current MCP specification only defines stdio and streamable HTTP. This server only offers streamable HTTP at `/mcp`. If a client can only speak SSE or stdio, bridge to the hosted URL with the community [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) package.
:::

## Self-Hosting

If you prefer to run your own instance, see the [Self-Hosting guide](/guide/self-hosting). Self-hosted servers use **stdio** transport for local connections.
