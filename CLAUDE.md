# Vue Documentation MCP Server — Complete Project Specification

---

## 1. Project Vision

Build an MCP (Model Context Protocol) server that serves as the world's best retrieval interface for the Vue.js documentation. Given a developer query, the server returns **reconstructed, readable documentation fragments** — not disconnected text chunks — preserving section structure, code examples, images, and contextual hierarchy. The server exposes scoped search tools that allow an LLM to intelligently route queries to the appropriate documentation section, decompose complex questions, and receive results ordered by the documentation's natural pedagogical flow.

---

## 2. Core Design Principles

**Structure-aware, not token-aware.** Every chunking and retrieval decision respects the documentation's inherent hierarchy: page > section > subsection > block (text / code / image). Fixed-size token chunking is explicitly avoided.

**Readable reconstruction, not ranked fragments.** Retrieved results are reassembled into coherent mini-documents using metadata (breadcrumbs, ordering indices, parent/sibling relationships), returned in the documentation's natural reading order rather than ranked by relevance score alone.

**Deterministic where possible, LLM where necessary.** API entity extraction, cross-reference parsing, and markdown structure analysis use deterministic methods. LLM calls are reserved for contextual enrichment, summary generation, and hypothetical question generation — tasks where semantic understanding is genuinely required.

**Hybrid retrieval as default.** Every search combines dense semantic embeddings, BM25 sparse/keyword search, and API entity metadata boosting. No single retrieval method is trusted alone.

**Unified embedding space.** All content types — prose, code, images, summaries, HyPE questions — live in a single vector space using one multimodal embedding model. No separate code or image embedding models. This eliminates score comparison problems, dual-search complexity, and query-routing ambiguity. A query like "how do I use ref in a template" gets one embedding and one search, with scores directly comparable across content types.

**Cost-conscious by design.** The system is designed for a commercial product at $10/1000 interactions. Per-query API costs must stay under $0.001. This rules out expensive per-search rerankers and favors token-based pricing, cheap LLMs for query transformation, and deterministic processing wherever possible.

**Incremental by design.** The indexing pipeline is built for incremental updates from the start, with content hashing at every layer to avoid unnecessary reprocessing.

---

## 3. Source Corpus: Vue.js Documentation

The Vue.js documentation lives in a GitHub repository as a collection of markdown files organized in a folder hierarchy. The primary content areas include getting started guides, essentials, component documentation, reusability patterns, built-in components, scaling guidance, TypeScript integration, advanced topics, a tutorial, examples, and a comprehensive API reference.

Each markdown file typically contains a mix of prose explanations, fenced code blocks (Vue SFC, JavaScript, TypeScript, HTML, CSS), occasional images/diagrams, internal cross-reference links to other doc pages, and API name references in backtick-wrapped inline code.

The documentation presents many pages in dual-track format, showing both Composition API and Options API variants. This must be captured as metadata on every chunk.

---

## 4. Technology Stack

### 4.1 Vector Database: Qdrant

Selected for: native multi-vector support (dense + sparse in one collection), built-in hybrid search with prefetch and RRF fusion, payload indexing for metadata filtering, existing MCP server implementations in the ecosystem, hosted cloud offering for production deployment.

### 4.2 Search Foundation: Jina AI (Unified Provider)

The entire search infrastructure layer — embedding and reranking — uses Jina AI. This provides a single vendor, single API key, single token pool, and critically, a single embedding space for all content types.

**jina-embeddings-v4** (3.8B parameters) — Universal multimodal embedding model supporting text, code, and images in a single vector space. Supports 32K token context, task-specific LoRA adapters (retrieval_document, retrieval_query, code retrieval), and Matryoshka dimensionality reduction for storage optimization. This replaces the need for separate text and code embedding models.

**jina-reranker-v3** (0.6B parameters) — SOTA listwise reranker achieving 61.94 nDCG@10 on BEIR and 63.28 on CoIR (code retrieval). Processes up to 64 documents simultaneously within 131K token context. Priced per token (shared token pool with embeddings), approximately $0.00024 per rerank call — an order of magnitude cheaper than Cohere's per-search pricing ($0.002/search).

**jina-reranker-m0** — Multimodal reranker for visual document ranking. Available as a future enhancement for image-heavy queries if needed.

**BM25 sparse vectors** — Generated via Qdrant's built-in BM25 embedding function or `bm25s` library. No external API needed.

**Pricing model:** Jina uses a unified token pool across all APIs (embedding, reranking, reader, classifier). Tokens are purchased in packages. Both embedding and reranking costs are token-based, not per-search, making them predictable and cost-effective.

### 4.3 LLM for Query-Time Processing: Gemini 2.5 Flash Lite

All query-time LLM tasks (sub-question decomposition, multi-query rewriting, step-back prompting, intent classification) use **Gemini 2.5 Flash Lite** at $0.10/M input tokens and $0.40/M output tokens. The three parallel query transformation calls complete in approximately 1 second at a combined cost of ~$0.00025.

### 4.4 LLM for Indexing-Time Processing: Gemini 2.5 Flash (or equivalent)

Indexing-time tasks (contextual enrichment, HyPE question generation, summary generation) use a slightly more capable but still cost-effective model. These run in batch during indexing, not at query time, so latency is less critical than quality. Gemini 2.5 Flash, Claude Haiku, or GPT-4o-mini are all viable.

### 4.5 LLM for Evaluation: Gemini 2.5 Pro (or equivalent)

Test dataset generation and LLM-as-judge evaluation use a large-context model like Gemini 2.5 Pro (1M+ token context window) to ingest a significant portion of the Vue documentation in a single prompt.

### 4.6 MCP SDK & Application Framework

**FastMCP** for the MCP server (Python). **Typer** + **Rich** for the ingestion CLI. TypeScript aligns with the Vue ecosystem; Python offers richer ML tooling. If a TypeScript MCP server variant is needed later for npm distribution, it can be added as a separate package.

### 4.7 Markdown Parsing

`markdown-it-py` — a faithful Python port of markdown-it with a token/tree API. Provides heading hierarchy, fenced code block extraction with language tags, image references, and link targets.

### 4.8 Cost Model Per Query

| Component | Tokens | Cost |
|---|---|---|
| 3× Gemini Flash Lite (decompose + rewrite + step-back, parallel) | ~800 in, ~400 out | $0.00025 |
| 1× Jina embedding (query) | ~50 | $0.000001 |
| 1× Qdrant hybrid search | — | $0 (fixed hosting) |
| 1× Jina reranker v3 (query + ~40 candidates) | ~12,000 | $0.00024 |
| **Total per query** | | **~$0.0005** |

At 1,000 interactions for $10 revenue: $0.50 in API costs, leaving $9.50 for server hosting and margin. Approximately 2x headroom against the $0.001/query budget.

### 4.9 Dependencies

| Need | Library | Why |
|---|---|---|
| MCP server | `fastmcp` | Lightweight, known, handles MCP protocol |
| Data models | `pydantic` + `pydantic-settings` | Validation, serialization, config management |
| Markdown parsing | `markdown-it-py` | Heading hierarchy, code blocks, links, images |
| Vector DB | `qdrant-client` | Official, full-featured, async support |
| Async HTTP | `httpx` | For Jina/Gemini API calls, parallel execution |
| Fuzzy matching | `rapidfuzz` | Entity dictionary matching with typo tolerance |
| BM25 | `bm25s` | Lightweight BM25 sparse vector generation |
| CLI | `typer` + `rich` | Ingestion pipeline CLI with progress bars |

**Not using:** LangChain, LlamaIndex, sentence-transformers, transformers, torch. The Jina and Gemini interactions are just HTTP requests. RRF fusion is ~20 lines of Python. Keeping the dependency tree shallow makes deployment and debugging dramatically simpler.

---

## 5. Project Structure

### 5.1 Monorepo Layout

```
vue-docs-mcp/
├── pyproject.toml                  # Root workspace config (uv workspace, dev deps, pytest config)
├── uv.lock
├── .env.example                    # JINA_API_KEY, GEMINI_API_KEY, QDRANT_URL, etc.
├── .gitignore
│
├── packages/
│   ├── core/                       # Shared library — models, clients, utilities
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── vue_docs_core/
│   │           ├── __init__.py
│   │           ├── config.py               # Pydantic Settings: env vars, API keys, Qdrant URL
│   │           ├── models/
│   │           │   ├── __init__.py
│   │           │   ├── chunk.py            # Chunk, ChunkMetadata, ChunkType enum
│   │           │   ├── entity.py           # ApiEntity, EntityIndex, EntityType enum
│   │           │   ├── crossref.py         # CrossReference, CrossRefType enum
│   │           │   └── query.py            # QueryIntent enum, QueryTransformResult, SearchResult
│   │           ├── clients/
│   │           │   ├── __init__.py
│   │           │   ├── jina.py             # Async wrapper: embed(), rerank()
│   │           │   ├── gemini.py           # Async wrapper: transform_query(), enrich(), generate_hype()
│   │           │   └── qdrant.py           # Collection setup, upsert, hybrid_search(), get_by_ids()
│   │           ├── parsing/
│   │           │   ├── __init__.py
│   │           │   ├── markdown.py         # MD file → List[Chunk] with heading hierarchy
│   │           │   ├── entities.py         # Deterministic API entity extraction from chunks
│   │           │   ├── crossrefs.py        # Internal link extraction from chunks
│   │           │   └── sort_keys.py        # Sidebar config → global sort key computation
│   │           └── retrieval/
│   │               ├── __init__.py
│   │               ├── entity_matcher.py   # Query-time dictionary matching with rapidfuzz
│   │               ├── fusion.py           # RRF implementation for multi-query fusion
│   │               ├── expansion.py        # Cross-reference expansion logic
│   │               └── reconstruction.py   # Sort-key ordering, merge adjacent, format response
│   │
│   ├── ingestion/                  # CLI tool — offline batch indexing pipeline
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── vue_docs_ingestion/
│   │           ├── __init__.py
│   │           ├── cli.py                  # Typer CLI: run, status
│   │           ├── scanner.py              # File discovery, hash comparison, change detection
│   │           ├── enrichment.py           # LLM enrichment orchestration (contextual, HyPE, summaries)
│   │           ├── embedder.py             # Batch embedding via Jina, BM25 generation
│   │           ├── indexer.py              # Qdrant upsert orchestration (chunks, HyPE points, summaries)
│   │           ├── pipeline.py             # Full pipeline: scan → parse → enrich → embed → store
│   │           └── state.py                # Hash store persistence (JSON or SQLite)
│   │
│   └── server/                     # MCP server — online query handling
│       ├── pyproject.toml
│       └── src/
│           └── vue_docs_server/
│               ├── __init__.py
│               ├── main.py                 # FastMCP app setup, tool registration, startup hooks
│               ├── tools/
│               │   ├── __init__.py
│               │   ├── search.py           # vue_docs_search tool implementation
│               │   ├── api_lookup.py       # vue_api_lookup tool implementation
│               │   ├── page.py             # vue_get_page tool implementation
│               │   ├── topics.py           # vue_list_topics tool implementation
│               │   └── related.py          # vue_get_related tool implementation
│               ├── pipeline.py             # Query pipeline orchestration (steps 1-11)
│               └── startup.py              # Load entity dict, synonym table, connect Qdrant
│
├── data/
│   ├── vue-docs/                   # Cloned vuejs/docs repo (gitignored, pulled by ingestion CLI)
│   ├── entity_dictionary.json      # Built by ingestion, read by server
│   ├── synonym_table.json          # Manually curated + LLM-generated, checked into git
│   ├── crossref_graph.json         # Built by ingestion, read by server
│   └── state/
│       └── index_state.json        # Hash store for incremental updates
│
├── tests/                          # Root-level test suite
│   ├── __init__.py
│   └── test_models.py             # Model instantiation and validation tests
│
├── eval/                           # Evaluation suite
│   ├── pyproject.toml
│   ├── generate_questions.py       # Use Gemini Pro to generate test dataset
│   ├── run_eval.py                 # Run queries through MCP server, judge with LLM
│   ├── questions.json              # Generated test dataset (checked in after review)
│   └── results/                    # Eval results per run (gitignored)
│
└── scripts/
    ├── bootstrap.sh                # Clone vue docs, initial setup
    └── inspect_chunks.py           # Debug utility: show chunks for a given doc page
```

### 5.2 Why This Structure

**uv workspaces** (`packages/core`, `packages/ingestion`, `packages/server`) allow each package to declare its own dependencies while sharing the core library. The ingestion pipeline needs `typer` and batch processing utilities; the server needs `fastmcp`; both depend on core. uv resolves the dependency graph across the workspace.

**`data/` is the shared state** between ingestion and server. The ingestion pipeline writes here; the server reads at startup. The entity dictionary, synonym table, and crossref graph are lightweight JSON files that the server loads into memory. The heavy data (embeddings, chunk content) lives in Qdrant.

**`eval/` is a separate package**, not part of the runtime. It imports the server's query pipeline to run end-to-end evaluation but is never deployed.

### 5.3 Dependency Configuration

All packages use `hatchling` as the build backend and Python >=3.13. Workspace dependencies use `[tool.uv.sources]` with `{ workspace = true }`.

**packages/core:**
```toml
[project]
dependencies = [
    "pydantic>=2.12",
    "pydantic-settings>=2.13",
    "qdrant-client>=1.17",
    "httpx>=0.28",
    "markdown-it-py>=4.0",
    "rapidfuzz>=3.14",
    "bm25s>=0.3",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/vue_docs_core"]
```

**packages/ingestion:**
```toml
[project]
dependencies = [
    "vue-docs-core",
    "typer>=0.24",
    "rich>=14.3",
]

[tool.uv.sources]
vue-docs-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/vue_docs_ingestion"]
```

**packages/server:**
```toml
[project]
dependencies = [
    "vue-docs-core",
    "fastmcp>=3.1",
]

[tool.uv.sources]
vue-docs-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/vue_docs_server"]
```

**Root pyproject.toml:**
```toml
[project]
name = "vue-docs-mcp"
requires-python = ">=3.13"
dependencies = [
    "vue-docs-core",
    "vue-docs-ingestion",
    "vue-docs-server",
]

[tool.uv.sources]
vue-docs-core = { workspace = true }
vue-docs-ingestion = { workspace = true }
vue-docs-server = { workspace = true }

[tool.uv.workspace]
members = ["packages/*"]

[dependency-groups]
dev = [
    "pytest>=9.0",
    "pytest-asyncio>=1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

## 6. Indexing Pipeline

### 6.1 Document Scanning & Change Detection

On each indexing run, scan all markdown files in the repository. Compute a SHA-256 hash of each file's raw markdown content. Compare against stored hashes from the previous run. Files with unchanged hashes are skipped entirely.

A `pipeline_version` identifier is maintained alongside the hashes. Bumping this version (when changing chunking strategy, embedding model, enrichment prompts, or any processing logic) forces a full re-index of all files regardless of content hashes.

Per-file metadata stored between runs: content hash, last indexed timestamp, list of chunk IDs originating from the file, and the pipeline version used.

### 6.2 Markdown Parsing & Structural Chunking

Parse each markdown file using `markdown-it-py`. Walk the token stream to decompose the document into structural chunks at natural boundaries.

**Chunk types and their boundaries:**

*Section chunks* are defined by H2 (`##`) headings. Each H2 and all content beneath it (until the next H2 or end of file) becomes one chunk. This is the primary retrieval unit.

*Subsection chunks* are defined by H3/H4 headings within a section. These provide finer granularity for targeted retrieval.

*Code block chunks* extract each fenced code block as a separate chunk. The code block retains its language tag (vue, js, ts, html, css) and is paired with the immediately preceding paragraph of prose. This pairing is stored in the chunk metadata so that code is never returned without its explanation.

*Image chunks* extract each image reference with its alt text, caption (if any), and the surrounding paragraph context. For the MVP, the alt text and surrounding context serve as the searchable content. VLM-generated image descriptions can be added post-MVP.

*Page-level chunk* — the entire page is also stored as a single chunk (or a summary thereof) for broad thematic queries.

Every chunk carries a **metadata envelope** containing: a unique chunk ID derived from file path and heading text (e.g., `guide/essentials/computed#writable-computed`), the chunk level, file path, page title, section title, subsection title, the full breadcrumb string, parent/sibling/child chunk IDs, content type, language tag for code blocks, API style indicator (composition, options, both), and a **global sort key** encoding the chunk's position.

### 6.3 Global Sort Key

Each chunk receives a sort key that encodes its position in the full documentation hierarchy. The format is `{top_level_order}_{folder_order}_{file_order}_{heading_order}`. For example: `02_guide/01_essentials/03_computed/02_writable`. This key is used during reconstruction to order retrieved chunks in the documentation's reading flow.

The ordering is derived from the documentation's sidebar configuration (VitePress typically stores this in `.vitepress/config.ts`). Fall back to alphabetical order within folders if parsing fails.

### 6.4 Contextual Enrichment (Anthropic's Contextual Retrieval)

For each chunk, generate a short context prefix (2-3 sentences) using an LLM. The prompt receives the full page content and the specific chunk, and produces a summary that situates the chunk within the page — mentioning the Vue concept being discussed, any API names referenced, and how the chunk relates to the page's overall topic.

The generated context is prepended to the chunk text before embedding. It is stored as a separate field in the chunk metadata so it can be stripped when presenting results to the user.

This step is the most expensive per-chunk LLM call in the pipeline. Use prompt caching (send the full page once, then vary only the chunk portion across calls for the same page) to reduce cost and latency.

### 6.5 HyPE — Hypothetical Question Generation

For each chunk, generate 3-5 hypothetical developer questions that this chunk would answer. For example, a chunk about computed property caching might generate: "why is my computed not updating", "when does a computed property recalculate", "computed vs method performance vue", "how does computed caching work".

These questions are embedded using the same jina-embeddings-v4 model and stored as **separate points** in Qdrant with a `parent_chunk_id` reference back to the source chunk and a `chunk_type` of `hype_question`. Because they share the same embedding space, HyPE question points are discovered naturally during dense search. When a HyPE point matches a query, the system resolves it to the parent chunk for inclusion in results. This design avoids the complexity of multiple named vectors per point while keeping HyPE embeddings fully searchable.

This is an indexing-time investment that yields zero additional latency at query time. Initial research indicates up to 42% improvement in retrieval precision.

### 6.6 API Entity Extraction (Deterministic)

Extract Vue API entity references from every chunk using a two-tier approach (with a third tier deferred to post-MVP).

**Tier 1 — Inline code and headings.** Scan the markdown token stream for backtick-wrapped inline code tokens and heading text containing parentheses (function signatures). Match each extracted token against a curated Vue API dictionary. The dictionary is bootstrapped by scanning all H2/H3 headings in the `/api/` folder of the docs — each heading there is an API name.

**Tier 2 — Code block parsing.** For fenced code blocks, use regex patterns to extract imported identifiers (from `import { ref, computed } from 'vue'` statements), function calls, and directive usage (`v-model`, `v-for`, etc.). Match against the same dictionary. Regex is sufficient for this narrow extraction task.

**Tier 3 (future) — LLM-based implicit extraction.** For prose chunks that discuss an API concept without naming it, an LLM could infer the relevant APIs. Deferred to post-MVP.

The output per chunk is a list of explicit API entity references with their extraction source stored in the chunk payload metadata.

A **global API entity index** is also maintained: a dictionary mapping each Vue API name to the list of chunk IDs that reference it, along with a type classification (lifecycle_hook, composable, directive, component, compiler_macro, etc.) and a list of related APIs (e.g., `ref` relates to `reactive`, `unref`, `isRef`). This index is used for the `vue_api_lookup` fast-path tool.

### 6.7 Cross-Reference Extraction

Parse all markdown internal links (`[text](/guide/...)`, `[text](/api/...)`) from every chunk. Store as structured metadata on each chunk. Also build a global cross-reference graph: for each page/chunk, the set of pages/chunks it links to, and the reverse.

Classify each cross-reference by type based on source and target folder paths: guide-to-api and api-to-guide links are HIGH value, same-folder guide-to-guide links are MEDIUM value, cross-folder guide-to-guide links are LOW value. This classification is used during retrieval to determine expansion priority.

Cross-reference extraction is entirely deterministic (regex/AST parsing) and cheap. It is rebuilt fully on each indexing run rather than incrementally.

### 6.8 Hierarchical Summary Generation (RAPTOR-Inspired)

Build a multi-level summary tree using the existing folder structure as the primary clustering signal.

**Page summaries (Layer 1).** For each markdown file, generate an LLM summary (3-5 sentences) capturing what the page teaches, which APIs it covers, and what a developer would learn from reading it. Embed and store as a chunk at the page summary level.

**Folder summaries (Layer 2).** For each folder (e.g., `guide/essentials/`, `guide/components/`), concatenate all page summaries and generate an LLM summary. This captures the theme of the documentation section.

**Top-level summaries (Layer 3).** For each top-level documentation area (guide, api, tutorial, examples), generate a summary from the folder summaries. This is the most abstract level, used for very broad queries.

All summary nodes are embedded and stored in the same Qdrant collection as leaf chunks, with a `level` metadata field so that retrieval can search across all levels simultaneously.

### 6.9 Unified Embedding with Jina

All chunk types are embedded into a single vector space using **jina-embeddings-v4**. This model handles text, code, and images natively.

jina-embeddings-v4 supports task-specific LoRA adapters that optimize embeddings for different use cases without changing the output dimensionality. During indexing, prose chunks use the `retrieval_document` task, code block chunks use the code retrieval task, and queries use the `retrieval_query` task. All embeddings land in the same vector space and are directly comparable.

**BM25 sparse vectors** are generated for all chunks using `bm25s`, enabling keyword-based retrieval as a complementary signal to dense search.

### 6.10 Vector Database Storage (Qdrant)

Each chunk is stored as a single point in Qdrant with:

**Named vectors per point:** a single dense embedding vector (from jina-embeddings-v4) and a BM25 sparse vector. HyPE question embeddings are stored as separate points with a `parent_chunk_id` reference.

**Payload fields (indexed for filtering):** chunk_id, file_path, folder_path, chunk_type, content_type, api_style, api_entities (keyword array), global_sort_key.

**Payload fields (stored but not indexed):** raw content text, contextual enrichment prefix, breadcrumb string, cross-reference list, parent/child/sibling chunk IDs, preceding prose text (for code blocks).

A single Qdrant collection holds all chunk types and all RAPTOR levels.

### 6.11 Synonym / Alias Table

A lightweight deterministic lookup table mapping common developer phrases to Vue API entities. Built once (manually curated, checked into git) and stored as `data/synonym_table.json`.

Examples: "two-way binding" maps to `v-model`; "lifecycle" maps to `onMounted`, `onUnmounted`, `onBeforeMount`, etc.; "state management" maps to `reactive`, `ref`, `Pinia`; "template refs" maps to `ref`, `useTemplateRef`; "emit events" maps to `defineEmits`, `$emit`.

Used during query-time entity extraction to catch common conceptual phrases without requiring an LLM.

---

## 7. Incremental Update Strategy

### 7.1 Change Detection by Layer

**Layer 0 — Chunks.** Hash each file's raw markdown content. If hash is unchanged and pipeline version is unchanged, skip. If changed, delete all chunks from that file in the vector DB and regenerate.

**Layer 1 — Contextual enrichment.** Scoped to a single page, so changes don't cascade sideways. Regenerated whenever the parent file's chunks are regenerated.

**Layer 2 — Page summaries.** One-to-one with files. Regenerated whenever the file changes.

**Layer 3 — Folder summaries.** Hash the concatenation of all page summaries within the folder. If the combined hash is unchanged, skip. If changed, regenerate the folder summary and propagate upward to the parent folder.

**Layer 4 — Cross-references and API entity index.** Rebuilt fully on each run. Both are deterministic and fast (seconds for the full corpus).

### 7.2 Tombstone Handling

When a markdown file is deleted, all its chunks are removed from the vector DB by file path filter. Its contribution to folder summaries triggers regeneration. Cross-references pointing to the deleted file are cleaned up in the full rebuild.

### 7.3 Pipeline Version Bump

When the chunking strategy, embedding model, enrichment prompt, or any processing logic changes, the pipeline version is bumped. This forces a complete re-index of all files.

### 7.4 Typical Update Cost

For the Vue docs corpus (~100-150 markdown files), a typical update where 3-5 files changed involves approximately 15-25 LLM calls, re-embedding of 20-40 chunks, and a full cross-reference + entity index rebuild. Expected processing time: 1-2 minutes. Expected API cost: a few cents.

---

## 8. Query Pipeline

### 8.1 Step 1 — Query-Time Entity Extraction

Before any LLM calls, run a fast dictionary scan against the query text. Normalize the query (lowercase, strip backticks), tokenize on whitespace/punctuation, and match each token (and bigrams for compound names like `watchEffect`) against the curated Vue API dictionary using case-insensitive comparison. Include basic fuzzy matching (Levenshtein distance ≤ 2) to catch typos like "definProps" or "onmounted." Also check the synonym/alias table for conceptual phrase matches.

This runs in sub-millisecond time, requires no LLM, and produces a list of detected API entities to be used as metadata boost filters in retrieval.

### 8.2 Step 2 — Intent Classification

Classify the query into one of six intent categories to determine which pipeline path to follow. This can be done by the calling LLM (as part of its tool-use reasoning), encoded as a parameter on the MCP tool, or determined by a heuristic based on entity detection and query patterns.

**API Lookup** — Query contains a recognized API name and asks for its signature/behavior. Route to exact-match API entity index as primary path.

**How-To** — Query asks how to accomplish a task. Route to guide sections, prioritize chunks with code examples.

**Conceptual** — Query asks for explanation of a principle or system. Apply step-back prompting, retrieve from RAPTOR summary nodes as well as leaf chunks.

**Debugging** — Query describes a symptom or unexpected behavior. Apply step-back prompting to retrieve conceptual context. HyPE question embeddings (generated at indexing time) bridge the vocabulary gap between developer symptoms and documentation explanations.

**Comparison** — Query asks about differences or trade-offs between multiple concepts. Decompose into parallel sub-queries, one per concept.

**Migration** — Query asks about converting between patterns. Search across both API pattern tracks with broad scope.

### 8.3 Step 3 — Query Transformation

Based on the classified intent, apply one or more transformations before retrieval.

**Sub-question decomposition.** For multi-faceted queries, use an LLM to break the query into independent sub-questions. Each sub-question is retrieved separately, and results are fused.

**Multi-query rewriting.** Generate 3-5 reformulations of the same query to improve recall. Covers different phrasings, synonym usage, and specificity levels.

**Step-back prompting.** Generate a more general, conceptual version of the question. Retrieves broader context that helps explain the specific issue.

All three transformations are executed as **parallel calls to Gemini 2.5 Flash Lite**, keeping total query transformation latency to approximately 1 second regardless of how many are activated. Combined cost: approximately $0.00025.

Note: HyDE (Hypothetical Document Embedding) was considered and deliberately excluded. HyDE adds per-query LLM latency and risks hallucination-driven retrieval misdirection. The vocabulary gap is addressed at indexing time via HyPE, which has zero query-time overhead.

### 8.4 Step 4 — Scoped Retrieval

Each (sub-)query is routed to the appropriate documentation scope. Scoping is implemented as a Qdrant payload filter on the `folder_path` field.

For each query (or sub-query), run three retrieval methods in parallel within Qdrant:

**Dense semantic search** using the unified jina-embeddings-v4 vector. Because all content types share the same embedding space, a single search covers everything. Retrieve top-30.

**BM25 sparse search** using the sparse vector. Retrieve top-30. Essential for exact API name matching and technical terminology.

**Entity metadata boost.** If API entities were detected in the query, apply a Qdrant payload filter condition (`api_entities contains [detected entities]`) as a `should` filter, boosting matching chunks without excluding others.

All three methods execute as a single Qdrant query using the `prefetch` + `fusion` mechanism with Reciprocal Rank Fusion (RRF).

### 8.5 Step 5 — Fusion Across Sub-Queries

If the query was decomposed into sub-queries, apply RRF across all sub-query result sets to produce a single unified candidate list. Deduplicate by chunk ID, keeping the highest fused score. For any HyPE question points in the results, resolve them to their parent chunks. Target: approximately 30-40 unique candidates after fusion.

### 8.6 Step 6 — Cross-Reference Expansion

For the top-10 highest-scoring candidates, follow their outgoing cross-references to pull in additional relevant chunks.

**Expansion rules:** HIGH-value links (guide ↔ api): always follow. MEDIUM-value links (same-folder guide → guide, api → api): follow only for top-10 candidates. LOW-value links (cross-folder guide → guide): follow only for top-5 candidates. Never follow cross-references of cross-references (one hop only).

After expansion and deduplication, target: approximately 40-55 unique candidates.

### 8.7 Step 7 — Reranking

Pass the deduplicated candidate set through **jina-reranker-v3**. This listwise reranker processes the query and all candidate documents in a single context window (up to 131K tokens), enabling cross-document comparison for better ranking quality.

For a typical rerank call (~12,000 tokens total), cost is approximately $0.00024. Select the top 15-20 chunks after reranking.

### 8.8 Step 8 — Reconstruction & Ordering

Transform the flat list of top-ranked chunks into a structured, readable response.

**Group** chunks by source page. **Sort** by global sort key, not by relevance score — introductory material precedes advanced topics. **Merge** adjacent chunks from the same section. **Attach** code examples to their explanatory text. **Place** RAPTOR summary nodes as section introductions. **Include** cross-reference "See also" pointers. **Strip** the contextual enrichment prefix (user sees original doc text).

### 8.9 Step 9 — Response Format

Return a structured response with: a top-level summary of what was found, result sections each containing breadcrumb path, source URL, section title, content (prose + code interleaved), code examples as separate structured objects with language tag and description, image references, relevant API entities, "See also" cross-references, and API style indicator.

---

## 9. MCP Server Design

### 9.1 Primary Tool

**`vue_docs_search`** — The primary search tool. Parameters: `query` (string, required), `scope` (string, defaults to "all" — can be "guide", "guide/essentials", "api", or any folder path), `max_results` (integer, defaults to 10).

### 9.2 Auxiliary Tools

**`vue_api_lookup`** — Fast-path exact match for API references. Accepts `api_name` (string). Bypasses vector search entirely, goes straight to the API entity index.

**`vue_get_page`** — Retrieve an entire documentation page by path. Useful when the LLM needs full context.

**`vue_list_topics`** — Return the documentation table of contents for a given scope.

**`vue_get_related`** — Given a topic or API name, return related documentation using the cross-reference graph and the API entity "related" field.

### 9.3 MCP Resources

Expose the documentation table of contents and API index as MCP resources.

### 9.4 Error Handling & Fallbacks

If the initial retrieval yields no results above a minimum confidence threshold: (1) retry with a broader scope, (2) apply multi-query rewriting with more aggressive reformulation, (3) return the most relevant RAPTOR summary node. The response should always include something useful — never return empty.

---

## 10. Evaluation Framework

### 10.1 Test Dataset

Generate a benchmark of 200+ queries using Gemini 2.5 Pro with 1M+ token context. Feed a substantial portion of the Vue documentation into the model and prompt it to generate challenging, diverse questions across all intent types. For each generated question, the model also produces a ground-truth answer with explicit references to the documentation sections it drew from.

### 10.2 Metrics

**Retrieval quality:** Recall@K (K=5, 10, 20), NDCG@10.

**End-to-end answer quality (primary metric):** Provide the reconstructed context to an LLM, have it answer the query. Use LLM-as-judge to evaluate answer correctness against ground truth.

**Latency:** End-to-end query time, broken down by stage. Target: under 2 seconds P95.

**Cost tracking:** Actual API cost per query, tracked in production. Alert if average exceeds $0.0008.

### 10.3 Ablation Testing

Systematically disable each component and measure impact: contextual enrichment, HyPE questions, entity metadata boosting, cross-reference expansion, reranking, query transformation, summaries.

---

## 11. Implementation Plan

### Phase 1 — Foundation MVP (Week 1)

**Goal:** Working end-to-end vertical slice — markdown in, MCP tool responses out. No enrichment, no reranking, no query transformation. Prove the core loop works.

---

**Day 1 — Project scaffold + Pydantic models**

Set up the monorepo structure with uv workspaces. Create the three packages with their `pyproject.toml` files. Verify `uv sync` resolves everything.

Write the core Pydantic models:
- `ChunkType` enum: `section`, `subsection`, `code_block`, `image`, `page_summary`, `folder_summary`, `top_summary`, `hype_question`
- `ChunkMetadata`: file_path, folder_path, page_title, section_title, subsection_title, breadcrumb, global_sort_key, content_type, language_tag, api_style, api_entities list, cross_references list, parent_chunk_id, sibling_chunk_ids, child_chunk_ids, preceding_prose
- `Chunk`: chunk_id, chunk_type, content, metadata, contextual_prefix (optional), hype_questions (optional), content_hash
- `ApiEntity`: name, entity_type (EntityType enum), page_path, section, related list
- `EntityType` enum: `lifecycle_hook`, `composable`, `directive`, `component`, `compiler_macro`, `global_api`, `option`, `instance_method`, `instance_property`, `other`
- `EntityIndex`: entities dict, entity_to_chunks dict
- `CrossReference`: source_chunk_id, target_path, link_text, ref_type (HIGH, MEDIUM, LOW)
- `SearchResult`: chunk, score, retrieval_method
- `QueryIntent` enum: `api_lookup`, `conceptual`, `howto`, `debugging`, `comparison`, `migration`, `auto`

Also write `config.py` with Pydantic Settings and `.env.example`.

**Exit: `uv run pytest` passes with model instantiation tests.**

---

**Day 2 — Markdown parser**

Write `parsing/markdown.py`: `parse_markdown_file(path: Path) -> list[Chunk]` that:

1. Reads the file, parses with `markdown-it-py` into a token stream.
2. Walks tokens to identify the heading hierarchy, builds a stack-based heading context.
3. Splits content at H2 boundaries into section chunks; within each section, splits at H3 boundaries into subsection chunks.
4. Extracts fenced code blocks as separate `code_block` chunks, each tagged with language and the immediately preceding paragraph.
5. Extracts image tokens as `image` chunks with alt text and surrounding paragraph.
6. Generates chunk IDs from `{relative_file_path}#{heading_slug}`.
7. Computes parent/child/sibling relationships from the heading hierarchy.
8. Detects API style (composition/options/both) by looking for common markers.

Write `scripts/inspect_chunks.py` — debug utility that runs the parser on a file and prints chunks with metadata using `rich`.

Clone the Vue docs repo. Run the parser against 5-10 representative pages. Fix edge cases.

**Exit: `inspect_chunks.py guide/essentials/computed.md` produces clean, correctly-hierarchied chunks.**

---

**Day 3 — Entity extraction + cross-reference parsing + sort keys**

Write `parsing/entities.py`: scan chunk content for backtick-wrapped tokens and code block import patterns, match against API dictionary. Bootstrap the dictionary by scanning H2/H3 headings in `/api/`. Store as `data/entity_dictionary.json`.

Write `parsing/crossrefs.py`: find all internal markdown links, classify by source/target folder paths into HIGH/MEDIUM/LOW value.

Write `parsing/sort_keys.py`: parse the VitePress sidebar config to map each page path to a global sort key. Fall back to folder-alphabetical ordering.

Run entity extraction on the full corpus. Inspect the dictionary.

**Exit: Entity dictionary has ~200-300 entries. Cross-references and sort keys look correct.**

---

**Day 4 — Jina embedding client + BM25 + Qdrant collection setup**

Write `clients/jina.py`: async wrapper around Jina's embedding API with timeout, retry (3 attempts with exponential backoff), and rate limiting. Handle the task type parameter for jina-embeddings-v4 (`retrieval.passage` for documents, `retrieval.query` for queries).

Write BM25 sparse vector generation using `bm25s`. Fit on the full corpus vocabulary, save the fitted model to `data/`.

Write `clients/qdrant.py`: `setup_collection()`, `upsert_chunks()`, `hybrid_search()` (prefetch + RRF), `get_by_ids()`. Set up payload indices on `folder_path`, `chunk_type`, `api_entities`, `api_style`, `global_sort_key`.

Stand up a Qdrant instance. Run `setup_collection()`. Verify schema.

**Exit: Can embed, generate sparse vectors, and upsert to Qdrant. Collection schema matches the design.**

---

**Day 5 — Ingestion pipeline: end-to-end first run**

Write `ingestion/pipeline.py`: scanner (find .md files) → parser → entity extraction → cross-ref extraction → sort key assignment → embedding → BM25 → Qdrant upsert. Skip contextual enrichment, HyPE, summaries, incremental updates for now.

Write `ingestion/cli.py` with Typer: `vue-docs-ingest run --docs-path ./data/vue-docs/src --full` and `vue-docs-ingest status`.

Run the full pipeline on the entire Vue docs corpus. Use `rich` progress bars. Monitor for parsing failures, API rate limits, unexpectedly large/small chunks.

**Exit: All Vue docs indexed in Qdrant. `status` shows chunk counts by type and folder.**

---

**Day 6 — MCP server: basic search tool**

Write `server/main.py` with FastMCP setup. Write `server/startup.py`: loads entity dictionary, synonym table, BM25 model, connects Qdrant.

Write `server/tools/search.py`: the `vue_docs_search` tool — embed query via Jina, generate BM25 sparse vector, run `hybrid_search()` with scope filter, format results.

Write `retrieval/reconstruction.py`: sort results by global_sort_key, group by page, format with breadcrumb headers and code blocks.

Connect to Claude Code. Ask Vue documentation questions. Verify relevant results in readable format.

**Exit: Working MCP server that Claude Code can connect to. Vue questions return relevant results.**

---

**Day 7 — Entity matching + entity boost + synonym table**

Write `retrieval/entity_matcher.py`: normalize, tokenize, exact match, bigram match, fuzzy match with rapidfuzz, synonym lookup.

Create `data/synonym_table.json` manually (20-30 entries).

Integrate entity matching into the search tool: detected entities become a `should` filter in the Qdrant query.

Write `server/tools/api_lookup.py`: the `vue_api_lookup` fast-path tool.

**Exit: "What does defineEmits do?" triggers entity detection and returns the API reference. "two-way binding" matches via synonym table.**

---

**Day 8 — Reconstruction polish + evaluation baseline**

Improve reconstruction: code block rendering, adjacent chunk merging, source URLs, summary line.

Write `eval/generate_questions.py`: send Vue documentation to Gemini 2.5 Pro, generate 50+ test questions with ground-truth answers.

Write `eval/run_eval.py`: run questions through the search pipeline, judge with LLM, report metrics.

Run baseline evaluation. Record numbers.

**Exit: Baseline metrics established. Phase 1 complete.**

---

### Phase 2 — Enrichment & Retrieval Quality (Week 2)

**Goal:** Add every technique that measurably improves quality, validated after each addition.

---

**Day 9 — Contextual enrichment**

Write `ingestion/enrichment.py`: for each page, send full page content to Gemini Flash (gemini-2.5-flash-lite) with prompt caching, generate context prefix per chunk. Use async to parallelize across pages. Store prefix in `chunk.contextual_prefix`, prepend before embedding, strip for display.

Re-embed all enriched chunks. Re-upsert to Qdrant. Run eval. Compare to baseline.

**Exit: All chunks have contextual prefixes. Eval metrics improve over baseline.**

---

**Day 10 — HyPE question generation + indexing**

Extend enrichment with HyPE: generate 3-5 hypothetical questions per chunk via Gemini Flash (gemini-2.5-flash-lite). Embed each question via Jina. Store as separate points in Qdrant with `chunk_type: "hype_question"` and `parent_chunk_id`.

Update `hybrid_search()` to handle HyPE resolution: for HyPE results, swap for parent chunks, deduplicate.

Run eval. Check debugging and vague queries specifically.

**Exit: HyPE questions indexed. Eval shows improvement on debugging and vague queries.**

---

**Day 11 — Jina reranker integration**

Write reranker into `clients/jina.py`: `async def rerank(query, documents, top_n)`. Integrate between fusion and reconstruction.

Run eval. Compare RRF-only top-10 vs. reranked top-10. Measure latency impact.

**Exit: Reranking integrated. Eval confirms improvement. Latency within budget.**

---

**Day 12 — Cross-reference expansion**

Write `retrieval/expansion.py`: take top-10 results, look up cross-references, apply expansion rules (HIGH/MEDIUM/LOW value), fetch expanded chunks by ID, deduplicate. Expansion happens before reranking.

Update reconstruction to include "See also" links.

Run eval. Check multi-hop questions.

**Exit: Cross-reference expansion working. Multi-hop questions improve without precision degradation.**

---

**Day 13 — Page and folder summaries (RAPTOR layers)**

Write summary generation: page summaries (3-5 sentences each), folder summaries (from concatenated page summaries). Embed and upsert as `page_summary`/`folder_summary` chunks.

Run eval. Check broad conceptual questions.

**Exit: Summary layers indexed. Broad queries return summaries alongside detail chunks.**

---

**Day 14 — Incremental updates**

Write `ingestion/scanner.py`: file discovery and hash comparison. Write `ingestion/state.py`: hash store persistence.

Update pipeline for incremental mode: scan → detect changes → re-process only changed files → cascade summary updates → rebuild entity/crossref indices. Add CLI flags: `--full` (force rebuild), `--dry-run` (show what would change).

Test: modify one file, verify only that file is reprocessed.

**Exit: Incremental updates work correctly. Phase 2 complete.**

---

### Phase 3 — Query Intelligence & Production (Week 3)

**Goal:** Add query-time intelligence and harden for production.

---

**Day 15 — Query transformation: parallel Flash Lite calls**

Write `clients/gemini.py` query transformation functions: `decompose_query()`, `rewrite_query()`, `step_back_query()`. All return structured JSON output. All three run as `asyncio.gather()`.

Write intent classification (heuristic-based initially).

Update `server/pipeline.py` to wire in transformations: entity extraction → intent classification → parallel transformation → parallel retrieval per variant → RRF fusion → expand → rerank → reconstruct.

Run eval across all intent categories.

**Exit: Full query pipeline operational. Eval metrics significantly improved.**

---

**Day 16 — Additional MCP tools + scope refinement**

Implement `vue_list_topics`, `vue_get_related`, `vue_get_page`. Write clear tool descriptions for LLM routing. Test with multiple MCP clients.

**Exit: All four MCP tools operational. Tool routing works well in Claude Code.**

---

**Day 17 — Evaluation + ablation + latency profiling**

Expand eval dataset to 100+ questions. Run full ablation suite (disable each component, measure impact). Profile latency per stage. Measure actual per-query cost.

**Exit: Complete evaluation report. Know exactly what each component contributes.**

---

**Day 18 — Production hardening**

Error handling: Jina timeout → degrade gracefully (skip reranking), Gemini timeout → skip transformation, Qdrant loss → error message, empty results → scope escalation.

Structured request logging (JSON): query, entities, intent, latency, cost. Health check endpoint. Configuration via environment variables.

**Exit: Graceful degradation on all failure modes. Logging operational.**

---

**Day 19 — Documentation + deployment setup**

Write README.md: quickstart, MCP client configuration, architecture overview, development guide. Write deployment notes: Qdrant Cloud setup, env vars, ingestion commands, CI/CD design.

**Exit: New developer can set up the system in 30 minutes. Phase 3 complete.**

---

**Day 20 — Buffer / stretch goals**

Deliberately unplanned. Use for whichever provides the most value: fix the biggest quality issue from evaluation, tune chunk size thresholds, expand the synonym table, add API style filtering, set up CI/CD, or begin a TypeScript MCP server variant.

**Exit: The system is production-ready. Ship it.**

---

## 12. Open Questions

These are decisions to validate during implementation:

**Jina embeddings-v4 code quality.** Benchmark on Vue/TypeScript/JavaScript code retrieval queries. If insufficient, add CodeXEmbed 400M as a secondary named vector in Qdrant.

**Scope parameter vs. separate tools.** Test whether the calling LLM routes more accurately with one tool + scope parameter versus 3-4 separate scoped tools.

**Chunk size tuning.** H2-level may produce oversized or undersized chunks. Consider max threshold (~1500 tokens → split at H3) and min threshold (~100 tokens → merge with adjacent).

**HyPE storage strategy.** Validate that Qdrant's search efficiently handles separate HyPE points with parent-child resolution. Alternative: multiple named vectors per point.

**Number of HyPE questions per chunk.** 3-5 starting range. Tune based on evaluation.

**Jina token pool budgeting.** Monitor consumption carefully. Set up alerting on token consumption per query.

**Reconstruction simplicity.** Validate that sort-key ordering produces readable output when results span 4-5 different pages.

**Latency of parallel Flash Lite calls.** Profile P95. If >1.5s, combine decomposition+rewriting into one prompt or make transformations conditional.

---

## 13. Decisions Log

| Decision | Rationale |
|---|---|
| **Jina AI as unified search provider** (embedding + reranking) | Single vendor, single token pool, single embedding space. Token-based reranker pricing (~$0.00024/query) is 10x cheaper than Cohere's per-search pricing ($0.002/query). |
| **No separate code embedding model** | jina-embeddings-v4 handles code natively via task-specific LoRA. Avoids dual-space complexity. To be validated during spike week. |
| **No HyDE** | Per-query LLM cost and hallucination risk. Vocabulary gap addressed at indexing time via HyPE (zero query-time overhead). Can be reconsidered if evaluation shows specific categories underperforming. |
| **Gemini 2.5 Flash Lite for query-time LLM** | Extreme speed (~1s for 3 parallel calls) and cost ($0.10/M input). Combined query transformation cost: ~$0.00025. Well within budget. |
| **LLM-as-judge evaluation** | Faster and cheaper than human annotation. Gemini 2.5 Pro generates test questions and judges answer quality. |
| **Hosted deployment** | Commercial product ($10/1000 interactions). API-based models, hosted Qdrant, no self-hosting of ML models. |
| **Per-query cost target: $0.001** | $10/1000 interactions revenue, need headroom for hosting costs. Achieved: ~$0.0005/query average, 2x headroom. |
| **No LangChain/LlamaIndex** | Custom pipeline by design. Framework abstractions would be fought against more than they help. RRF is ~20 lines. Entity matching is dictionary lookup. |
| **Python-only stack** | FastMCP, Jina client, Gemini client, Qdrant client, markdown parsing — all Python. No JS/TS needed for MVP. TypeScript variant can be added later. |
