import { defineConfig } from "vitepress";
import llmstxt from "vitepress-plugin-llms";

export default defineConfig({
  title: "Vue Docs MCP",
  description:
    "Give your AI assistant deep, structured access to the entire Vue.js documentation",

  vite: {
    plugins: [llmstxt()],
  },
  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: "/logo.svg" }],
    ["meta", { property: "og:type", content: "website" }],
    ["meta", { property: "og:title", content: "Vue Docs MCP" }],
    [
      "meta",
      {
        property: "og:description",
        content:
          "MCP server providing semantic search over Vue.js documentation",
      },
    ],
    ["meta", { property: "og:url", content: "https://vue-mcp.org" }],
  ],

  cleanUrls: true,

  themeConfig: {
    logo: "/logo.svg",
    siteTitle: "Vue Docs MCP",

    nav: [
      { text: "Guide", link: "/guide/what-is-vue-mcp" },
      { text: "Clients", link: "/clients/" },
      { text: "Reference", link: "/reference/tools" },
    ],

    sidebar: [
      {
        text: "Introduction",
        items: [
          { text: "What is Vue Docs MCP?", link: "/guide/what-is-vue-mcp" },
          { text: "Getting Started", link: "/guide/getting-started" },
        ],
      },
      {
        text: "MCP Clients",
        link: "/clients/",
        collapsed: false,
        items: [
          { text: "Claude Code", link: "/clients/claude-code" },
          { text: "Claude Desktop", link: "/clients/claude-desktop" },
          { text: "Cursor", link: "/clients/cursor" },
          { text: "Windsurf", link: "/clients/windsurf" },
          { text: "VS Code (Copilot)", link: "/clients/vscode" },
          { text: "JetBrains", link: "/clients/jetbrains" },
          { text: "Zed", link: "/clients/zed" },
          { text: "Opencode", link: "/clients/opencode" },
          { text: "Gemini CLI", link: "/clients/gemini-cli" },
          { text: "ChatGPT", link: "/clients/chatgpt" },
        ],
      },
      {
        text: "Reference",
        items: [
          { text: "Tools", link: "/reference/tools" },
          { text: "Resources", link: "/reference/resources" },
          { text: "Prompts", link: "/reference/prompts" },
          { text: "How It Works", link: "/reference/how-it-works" },
        ],
      },
      {
        text: "Setup",
        items: [
          { text: "Self-Hosting", link: "/guide/self-hosting" },
        ],
      },
    ],

    socialLinks: [
      { icon: "github", link: "https://github.com/joelbarmettlerUZH/vue-mcp" },
    ],

    footer: {
      message:
        'Released under the <a href="https://github.com/joelbarmettlerUZH/vue-mcp/blob/main/LICENSE.md">FSL-1.1-ALv2 License</a>.',
      copyright: "Copyright &copy; 2025 Joel Barmettler",
    },

    search: {
      provider: "local",
    },

    editLink: {
      pattern:
        "https://github.com/joelbarmettlerUZH/vue-mcp/edit/main/docs/:path",
    },
  },
});
