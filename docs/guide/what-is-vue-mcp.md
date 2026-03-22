# What is Vue Docs MCP?

Vue Docs MCP is an [MCP server](https://modelcontextprotocol.io/) that gives AI assistants deep, structured access to the [Vue ecosystem documentation](https://vuejs.org/), including Vue.js, Vue Router, and more frameworks as they are added.

Instead of pasting docs into prompts or hoping the LLM's training data is current, you connect this server and let your AI assistant search, browse, and retrieve documentation on demand.

## The Problem

LLMs have a knowledge cutoff. The Vue ecosystem evolves. When you ask your AI assistant about Vue:

- It might reference outdated APIs or patterns
- It can't see recent additions or changes to the docs
- It hallucinates plausible-sounding but incorrect details
- It has no way to cite or verify its answers

## The Solution

Vue Docs MCP indexes the full documentation for each supported framework and exposes it through the Model Context Protocol. Your AI assistant can:

- **Search** for any topic with semantic understanding
- **Look up** specific APIs instantly (`ref`, `computed`, `useRouter`, etc.)
- **Browse** the documentation structure and read raw pages
- **Discover** related APIs, concepts, and patterns
- **Follow** guided workflows for debugging, comparison, and migration

All results include source references so you can verify them.

## Supported Frameworks

| Framework | Status | Description |
|---|---|---|
| [Vue.js](https://vuejs.org) | :white_check_mark: Available | Core framework: reactivity, components, Composition API |
| [Vue Router](https://router.vuejs.org) | :construction: In progress | Official router: navigation guards, dynamic routes |
| [Pinia](https://pinia.vuejs.org) | :calendar: Planned | Official state management |
| [VueUse](https://vueuse.org) | :calendar: Planned | Composition API utilities |
| [Nuxt](https://nuxt.com) | :calendar: Planned | Full-stack framework |

See the full roadmap on the [Frameworks](/reference/frameworks) page. Each framework gets its own set of tools, resources, and prompts. You can [enable or disable frameworks per session](/reference/frameworks).

## How It Works

The server combines multiple retrieval strategies for high-quality results:

1. **Structure-aware chunking.** Docs are parsed respecting their heading hierarchy. Code examples stay paired with their explanations.
2. **Hybrid search.** Every query runs dense semantic search (Jina embeddings) and BM25 keyword search simultaneously.
3. **Smart entity detection.** API names are detected deterministically with typo tolerance, synonym lookup, and bigram matching.
4. **Reranking.** Candidates are reranked by Jina for precision.
5. **Readable reconstruction.** Results are reassembled in documentation reading order, preserving the natural flow of the docs.

## Using the Hosted Server

The easiest way to use Vue Docs MCP is through the free hosted server:

**`mcp.vue-mcp.org`**

No API keys, no setup, no infrastructure. See [Getting Started](/guide/getting-started) to connect it to your AI client.

## Self-Hosting

If you prefer to run your own instance, see the [Self-Hosting guide](/guide/self-hosting). You'll need API keys for Jina AI, Google Gemini, and a Qdrant instance.
