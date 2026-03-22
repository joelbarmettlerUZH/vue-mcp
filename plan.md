# Plan: Remove Defensive Coding Patterns

Audit every try/except, silent fallback, and defensive guard across the codebase.
For each, verdict is one of: **REMOVE** (let it crash), **KEEP** (justified), or **TIGHTEN** (narrow the catch / make explicit).

---

## 1. Server package (`packages/server/`)

### 1a. `startup.py` — `_source_names()` catches `ValueError`, falls back to all sources
**Lines 59-65.** If `get_enabled_sources()` raises `ValueError` (invalid config), silently returns ALL sources.
**Verdict: REMOVE.** Invalid config should crash at startup, not silently serve everything.

### 1b. `startup.py` — `startup()` catches Qdrant connection failure
**Lines 285-297.** `except Exception as e: logger.warning(...)` when Qdrant is unreachable. Server starts anyway with broken search.
**Verdict: REMOVE.** If Qdrant isn't reachable, the server is useless. Crash at startup.

### 1c. `startup.py` — `_load_from_pg()` no-db fallback path
**Lines 273-281.** `if settings.database_url` → PG path, else → file fallback. Two completely separate code paths.
**Verdict: REMOVE the file fallback.** The file path (`_load_from_files`) is dead code in production. PG is mandatory. Remove `_load_from_files()`, `load_entity_dictionary()`, `load_synonym_table()` and require `DATABASE_URL`. For local dev, run a local PG (docker compose already provides one).

### 1d. `startup.py` — `hot_reload_loop` catches broad `Exception`
**Lines 339-341.** `except Exception: logger.exception(...)` in the reload loop.
**Verdict: KEEP.** Background loop must not crash the server. But **TIGHTEN**: log at error level (it already uses `logger.exception` which is error-level, so this is fine as-is).

### 1e. `startup.py` — BM25 model warning when not found in PG
**Lines 120-121.** `logger.warning("BM25 model not found in PG")` — continues with empty model.
**Verdict: REMOVE.** BM25 is required for hybrid search. If missing in PG, crash. Means ingestion hasn't run yet — that's a deployment error, not a runtime condition to handle gracefully.

### 1f. `tools/search.py` — embedding failure returns error string
**Lines 41-42.** `if not embed_result.embeddings: return "Error: Failed to generate query embedding."`
**Verdict: REMOVE.** Raise `ToolError` instead of returning an error string that looks like a result. The Jina client should raise on failure anyway; this guard shouldn't be needed.

### 1g. `tools/search.py` — reranking fallback
**Lines 247-266.** `except Exception: return hits` — if Jina reranking fails, silently falls back to fusion scores.
**Verdict: TIGHTEN.** This is a query-time call to an external API. Crashing the whole search because reranking failed is too harsh — the fusion scores are a reasonable fallback. But catch `httpx.HTTPStatusError | httpx.TimeoutException` specifically, not bare `Exception`. Log at error level, not warning.

### 1h. `tools/search.py` — scope fallback
**Lines 64-72.** If no results in a specific scope, expands to all docs.
**Verdict: KEEP.** This is intentional UX — broadening scope when narrow scope finds nothing. It communicates the fallback to the user via `ctx.warning`.

### 1i. `main.py` — `_register_concrete_resources` uses `contextlib.suppress(KeyError)` for stale resource removal
**Verdict: KEEP.** Race condition between state and resource registry. Resource may already have been removed. `KeyError` is the only expected exception.

---

## 2. Core package (`packages/core/`)

### 2a. `clients/jina.py` — retry with `except httpx.HTTPStatusError` and `except httpx.TimeoutException`
**Lines 77-113.** Retry loop for Jina API with exponential backoff. Re-raises non-retryable errors. Raises `RuntimeError` after exhausting retries.
**Verdict: KEEP.** Properly scoped, retries transient errors only, re-raises permanent ones. This is exactly how retry logic should work.

### 2b. `clients/jina.py` — `embed()` returns empty result for empty input
**Lines 121-122.** `if not texts: return EmbeddingResult(embeddings=[], total_tokens=0)`
**Verdict: REMOVE.** Callers should not pass empty lists. If they do, that's a bug — let it crash. Same for `embed_image` (line 156) and `rerank` (line 177).

### 2c. `clients/qdrant.py` — `upsert_chunks` returns early on empty input
**Lines 131-132.** `if not chunk_ids: return`
**Verdict: REMOVE.** Same principle. Callers passing empty data is a bug. Same for `delete_by_chunk_ids` (line 216), `delete_by_file_paths` (line 243), `scroll_by_chunk_ids` (line 284).

### 2d. `clients/qdrant.py` — `create_payload_index` catches `UnexpectedResponse` status 400
**Lines 109-119.** Catches "index already exists" error.
**Verdict: KEEP.** Qdrant has no `create_if_not_exists` API. This is the documented pattern. Re-raises non-400 errors.

### 2e. `clients/postgres.py` — BM25 model not found returns `False`
**Line 174.** `if row is None: logger.warning(...)` then `return False`.
**Verdict: TIGHTEN.** Remove the warning log. Let the caller decide what to do with `False`. The startup code (1e above) will crash if it gets `False`.

### 2f. `clients/bm25.py` — `is None` checks on `self._model`
**Lines 50, 83, 113.** Guards that check if model is loaded before using it.
**Verdict: TIGHTEN.** Instead of returning `0` for vocab_size or empty results for queries, raise an explicit error: "BM25 model not loaded". The model being None means startup failed — that should never happen in normal operation.

### 2g. `retrieval/expansion.py` — `_resolve_crossref_type` catches `ValueError`
**Lines 156-159.** If the crossref type string doesn't match the enum, defaults to `HIGH`.
**Verdict: KEEP.** This is parsing external data (Qdrant payloads). Unknown type → default priority is a reasonable choice for backward compatibility when new types are added.

### 2h. `retrieval/reconstruction.py` — `_are_adjacent` catches `ValueError | IndexError`
**Lines 65-70.** Parsing chunk IDs to check adjacency. If parsing fails, returns `False`.
**Verdict: KEEP.** Chunk ID format is a convention, not enforced by types. Parsing failure = "not adjacent" is correct behavior.

---

## 3. Ingestion package (`packages/ingestion/`)

### 3a. `cli.py` — `_get_db()` returns `None` when no `DATABASE_URL`
**Lines 27-28.** Allows running without a database.
**Verdict: REMOVE.** PG is mandatory. If `DATABASE_URL` is not set, crash with a clear error message.

### 3b. `cli.py` — `run` command broad exception handler
**Lines 122-135.** Catches `Exception` around pipeline, logs it, exits.
**Verdict: TIGHTEN.** Remove the try/except entirely. Let the exception propagate — Typer will show the traceback. The `finally` for DB cleanup can use a context manager instead.

### 3c. `cli.py` — `watch` command per-source exception handler
**Lines 171-189.** Catches `Exception` per source in the watch loop, continues to next source.
**Verdict: KEEP but TIGHTEN.** Long-running daemon should survive individual source failures. But log at `error` level and consider adding an error counter that crashes after N consecutive failures.

### 3d. `cli.py` — `status` command Qdrant exception
**Lines 260-268.** Swallows Qdrant connection error in status display.
**Verdict: REMOVE.** Status command should report what's actually running. If Qdrant is down, say so explicitly or crash — don't silently skip it.

### 3e. `pipeline.py` — per-file markdown parsing exception
**Lines 259-270.** `except Exception` per file, adds to `failed_files`, continues.
**Verdict: KEEP but TIGHTEN.** One corrupted markdown file shouldn't stop the whole pipeline. But after the loop, if `failed_files` is non-empty, raise an error with the list of failures instead of just printing them.

### 3f. `pipeline.py` — page content reading exception
**Lines 296-299.** `except Exception as exc: logger.warning(...)` — silently skips unreadable files.
**Verdict: REMOVE.** If we can't read a file we're supposed to index, that's an error. Let it crash.

### 3g. `pipeline.py` — `contextlib.suppress(Exception)` for page content loading
**Line 442.** Suppresses ALL exceptions when reading files for RAPTOR summaries.
**Verdict: REMOVE.** Same as 3f. File read failures should crash, not be silently swallowed.

### 3h. `pipeline.py` — bare `except Exception: pass` at end for Qdrant stats
**Lines 654-659.** Completely swallows exception when fetching final stats.
**Verdict: REMOVE.** Either get the stats or don't try. If Qdrant is down at this point, something is very wrong.

### 3i. `pipeline.py` — `_payload_to_chunk()` uses `.get()` with defaults everywhere
**Lines 77-100.** 24 `.get()` calls with empty-string or placeholder defaults.
**Verdict: TIGHTEN.** This reconstructs chunks from Qdrant payloads. Missing fields in stored data is a data corruption issue. Use direct key access (`payload["chunk_id"]`) for required fields. Keep `.get()` only for genuinely optional fields like `contextual_prefix`.

### 3j. `pipeline.py` — missing Gemini API key skips enrichment
**Lines 351-354.** `if not settings.gemini_api_key: skip enrichment`.
**Verdict: REMOVE.** Enrichment is not optional — it produces contextual prefixes and HyPE questions that are critical for search quality. Require the API key. If you want to run without enrichment, make that an explicit CLI flag, not a silent degradation.

### 3k. `pipeline.py` — source defaults to Vue
**Lines 132-135.** `if source is None: source = SOURCE_REGISTRY["vue"]`.
**Verdict: REMOVE.** The caller (CLI) should always pass the source explicitly. No magic defaults.

### 3l. `state.py` — dual backend (PG + file) with silent switching
**Entire file.** Has `if self._db` checks everywhere, silently choosing between backends.
**Verdict: REMOVE file backend.** PG is mandatory. Remove all the JSON file state management. State is always PostgreSQL.

### 3m. `enrichment.py` — per-chunk exception handlers in async tasks
**Lines 201-217, 274-284, 358-368, 445-455, 516-531.** Each catches `Exception`, logs warning, returns error marker.
**Verdict: KEEP but TIGHTEN.** These are concurrent Gemini API calls — one failure shouldn't block others. But: (1) catch specific Gemini/HTTP exceptions, not bare `Exception`, (2) log at error level, (3) after all tasks complete, if error rate exceeds a threshold (e.g. >50%), raise to fail the pipeline.

### 3n. `enrichment.py` — `.get()` with empty defaults for page_contents
**Lines 80, 144, 265.** `page_contents.get(file_path, "")` then checks `if not page_content`.
**Verdict: REMOVE.** Use direct access `page_contents[file_path]`. If a file_path is expected in the dict but missing, that's a pipeline bug. The caller should ensure all file paths are present.

### 3o. `embedder.py` / `indexer.py` — empty input guards
**Lines 56-57, 99-100 (embedder), 49-50, 103-104 (indexer).** `if not chunks: return`.
**Verdict: REMOVE.** Same as 2b/2c. Empty input = caller bug.

---

## 4. Summary of work

| Verdict | Count |
|---------|-------|
| REMOVE | 19 |
| KEEP | 7 |
| TIGHTEN | 7 |

### Order of execution

**Phase 1 — Server startup (high impact, standalone)**
1. Remove file-based fallback from `startup.py` (1c) — delete `_load_from_files`, `load_entity_dictionary`, `load_synonym_table`. Require `DATABASE_URL`.
2. Remove `_source_names()` try/except (1a) — let `ValueError` crash.
3. Remove Qdrant connection swallowing (1b) — let startup crash.
4. Remove BM25 missing-model tolerance (1e) — crash if not in PG.
5. Tighten BM25Model `is None` checks (2f) — raise explicit errors.
6. Clean up PG client BM25 warning (2e).

**Phase 2 — Ingestion pipeline (high impact, standalone)**
7. Remove file backend from `state.py` (3l) — PG only.
8. Require `DATABASE_URL` in CLI (3a) — crash without it.
9. Remove Gemini API key silent skip (3j) — require it or make explicit flag.
10. Remove `_payload_to_chunk` silent defaults (3i) — use direct key access for required fields.
11. Remove page content read exception swallowing (3f, 3g).
12. Remove bare `except: pass` for final stats (3h).
13. Remove source default-to-Vue (3k).
14. Remove CLI broad exception handler (3b).
15. Tighten watch command handler (3c).
16. Remove status command Qdrant swallowing (3d).
17. Tighten per-file parse exception handling (3e).

**Phase 3 — Enrichment and embedding (moderate impact)**
18. Tighten enrichment exception handlers (3m) — specific exceptions + error threshold.
19. Remove `.get()` defaults for page_contents (3n).
20. Remove empty-input guards in embedder/indexer (3o) and Jina/Qdrant clients (2b, 2c).

**Phase 4 — Query-time tools (low risk)**
21. Replace error-string return with `ToolError` in search (1f).
22. Tighten reranking fallback to specific exceptions (1g).
