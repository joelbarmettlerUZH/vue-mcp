# What is Vue Docs MCP?

Vue Docs MCP is an [MCP server](https://modelcontextprotocol.io/) that gives AI assistants deep, structured access to the entire [Vue.js documentation](https://vuejs.org/).

Instead of pasting docs into prompts or hoping the LLM's training data is current, you connect this server and let your AI assistant search, browse, and retrieve Vue documentation on demand.

## The Problem

LLMs have a knowledge cutoff. Vue.js evolves. When you ask your AI assistant about Vue:

- It might reference outdated APIs or patterns
- It can't see recent additions or changes to the docs
- It hallucinates plausible-sounding but incorrect details
- It has no way to cite or verify its answers

## The Solution

Vue Docs MCP indexes the full Vue.js documentation and exposes it through the Model Context Protocol. Your AI assistant can:

- **Search** for any Vue topic with semantic understanding
- **Look up** specific APIs instantly (`ref`, `computed`, `v-model`, etc.)
- **Browse** the documentation structure and read raw pages
- **Discover** related APIs, concepts, and patterns
- **Follow** guided workflows for debugging, comparison, and migration

All results include source references so you can verify them.

## How It Works

The server combines multiple retrieval strategies for high-quality results:

1. **Structure-aware chunking** — Vue docs are parsed respecting their heading hierarchy. Code examples stay paired with their explanations.
2. **Hybrid search** — Every query runs dense semantic search (Jina embeddings) and BM25 keyword search simultaneously.
3. **Smart entity detection** — API names are detected deterministically with typo tolerance, synonym lookup, and bigram matching.
4. **Reranking** — Candidates are reranked by Jina for precision.
5. **Readable reconstruction** — Results are reassembled in documentation reading order, not just ranked by score.

## Using the Hosted Server

The easiest way to use Vue Docs MCP is through the free hosted server:

**`mcp.vue-mcp.org`**

No API keys, no setup, no infrastructure. See [Getting Started](/guide/getting-started) to connect it to your AI client.

## Self-Hosting

If you prefer to run your own instance, see the [Self-Hosting guide](/guide/self-hosting). You'll need API keys for Jina AI, Google Gemini, and a Qdrant instance.
