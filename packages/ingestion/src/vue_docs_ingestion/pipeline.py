"""Full pipeline: scan → parse → enrich → embed → store.

Supports both full re-indexing and incremental updates.  In incremental mode
only changed/new files are re-processed through the LLM-heavy steps
(enrichment, HyPE, summaries).  Deterministic steps that need the full corpus
(BM25 fitting, entity index, crossref graph) always operate on all chunks —
we reload unchanged chunks from Qdrant for this purpose.

Deleted file detection removes stale chunks from both Qdrant and the state
file.  Summary regeneration cascades: a changed file triggers its page
summary, which may cascade to its folder and top-level summaries.
"""

import contextlib
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.gemini import GeminiClient
from vue_docs_core.clients.jina import JinaClient
from vue_docs_core.clients.qdrant import QdrantDocClient
from vue_docs_core.config import UPSERT_BATCH_SIZE, settings
from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType
from vue_docs_core.parsing.crossrefs import build_crossref_graph
from vue_docs_core.parsing.entities import (
    build_api_dictionary,
    build_entity_index,
    load_dictionary,
    save_dictionary,
)
from vue_docs_core.parsing.markdown import parse_markdown_file
from vue_docs_core.parsing.sort_keys import compute_sort_key, parse_sidebar_config
from vue_docs_ingestion.embedder import embed_dense, embed_hype_questions
from vue_docs_ingestion.enrichment import (
    enrich_chunks_contextual,
    generate_folder_summaries,
    generate_hype_questions,
    generate_page_summaries,
    generate_top_summaries,
)
from vue_docs_ingestion.indexer import upsert_chunks_batch, upsert_hype_batch
from vue_docs_ingestion.scanner import find_markdown_files, hash_file
from vue_docs_ingestion.state import FileState, IndexState

logger = logging.getLogger(__name__)
console = Console()

# Chunk types that belong to leaf content (not summaries)
_LEAF_TYPES = {
    ChunkType.SECTION.value,
    ChunkType.SUBSECTION.value,
    ChunkType.CODE_BLOCK.value,
    ChunkType.IMAGE.value,
}

# Summary chunk types produced during indexing
_SUMMARY_TYPES = {
    ChunkType.PAGE_SUMMARY.value,
    ChunkType.FOLDER_SUMMARY.value,
    ChunkType.TOP_SUMMARY.value,
}


def _payload_to_chunk(payload: dict) -> Chunk:
    """Reconstruct a Chunk from a Qdrant payload dict.

    Used to reload unchanged chunks so that deterministic steps (entity
    extraction, crossref graph, BM25) operate on the full corpus.
    """
    return Chunk(
        chunk_id=payload.get("chunk_id", ""),
        chunk_type=ChunkType(payload.get("chunk_type", "section")),
        content=payload.get("content", ""),
        metadata=ChunkMetadata(
            file_path=payload.get("file_path", ""),
            folder_path=payload.get("folder_path", ""),
            page_title=payload.get("page_title", ""),
            section_title=payload.get("section_title", ""),
            subsection_title=payload.get("subsection_title", ""),
            breadcrumb=payload.get("breadcrumb", ""),
            global_sort_key=payload.get("global_sort_key", ""),
            content_type=payload.get("content_type", "text"),
            language_tag=payload.get("language_tag", ""),
            api_style=payload.get("api_style", "both"),
            api_entities=payload.get("api_entities", []),
            cross_references=payload.get("cross_references", []),
            parent_chunk_id=payload.get("parent_chunk_id", ""),
            sibling_chunk_ids=payload.get("sibling_chunk_ids", []),
            child_chunk_ids=payload.get("child_chunk_ids", []),
            preceding_prose=payload.get("preceding_prose", ""),
        ),
        contextual_prefix=payload.get("contextual_prefix", ""),
        content_hash=payload.get("content_hash", ""),
    )


def _summary_input_hash(texts: list[str]) -> str:
    """Compute a hash of concatenated summary input texts."""
    combined = "\n".join(texts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


async def run_pipeline(
    docs_path: Path,
    data_path: Path,
    *,
    full: bool = False,
    dry_run: bool = False,
) -> None:
    """Run the ingestion pipeline with incremental update support.

    Stages:
      1. Discover markdown files + detect deleted files
      2. Detect which files need re-processing (hash + version comparison)
      3. Parse changed .md → Chunk objects
      4. Contextual enrichment for new/changed chunks (Gemini)
      5. HyPE question generation for new/changed chunks (Gemini)
      6. Reload unchanged chunks from Qdrant for full-corpus steps
      7. Generate RAPTOR summaries (only for affected pages/folders)
      8. Entity extraction + cross-reference extraction (full corpus)
      9. Delete stale chunks from Qdrant
     10. Fit BM25 on full corpus
     11. Embed new/changed chunks + summaries with Jina
     12. Upsert to Qdrant in batches
     13. Embed + upsert HyPE questions
     14. Persist state
    """
    pipeline_version = settings.pipeline_version
    state_path = data_path / "state" / "index_state.json"
    entity_dict_path = data_path / "entity_dictionary.json"
    bm25_model_path = data_path / "bm25_model"
    sidebar_config_path = docs_path.parent / ".vitepress" / "config.ts"

    # ---- Header -------------------------------------------------------------
    console.print("[bold blue]Vue Docs Ingestion Pipeline[/bold blue]")
    console.print(f"  docs_path        = {docs_path}")
    console.print(f"  data_path        = {data_path}")
    console.print(f"  pipeline_version = {pipeline_version}")
    console.print(f"  full re-index    = {full}")
    console.print(f"  dry run          = {dry_run}")
    console.print()

    if dry_run:
        console.print("[yellow]DRY RUN — no changes will be made[/yellow]\n")

    # ---- Step 1: Discover files + detect deletions --------------------------
    with console.status("Discovering markdown files..."):
        md_files = find_markdown_files(docs_path)
    current_files = {str(p.relative_to(docs_path)) for p in md_files}
    console.print(f"Found [green]{len(md_files)}[/green] markdown files")

    state = IndexState(state_path)
    previously_indexed = set(state.all_file_paths())
    deleted_files = previously_indexed - current_files

    if deleted_files:
        console.print(f"Deleted files detected: [red]{len(deleted_files)}[/red]")

    # ---- Step 2: Change detection -------------------------------------------
    to_process: list[Path] = []
    for path in md_files:
        rel = str(path.relative_to(docs_path))
        existing = state.get(rel)
        if (
            full
            or existing is None
            or existing.content_hash != hash_file(path)
            or existing.pipeline_version != pipeline_version
        ):
            to_process.append(path)

    unchanged_files = current_files - {str(p.relative_to(docs_path)) for p in to_process}
    up_to_date_count = len(unchanged_files)
    console.print(
        f"Files to process: [green]{len(to_process)}[/green], "
        f"up-to-date: [dim]{up_to_date_count}[/dim], "
        f"deleted: [red]{len(deleted_files)}[/red]"
    )

    if not to_process and not deleted_files:
        console.print("[green]Everything up-to-date. Nothing to do.[/green]")
        return

    if dry_run:
        if to_process:
            console.print("\n[yellow]Files that would be processed:[/yellow]")
            for p in to_process:
                console.print(f"  [green]+[/green] {p.relative_to(docs_path)}")
        if deleted_files:
            console.print("\n[yellow]Files that would be cleaned up:[/yellow]")
            for df in sorted(deleted_files):
                console.print(f"  [red]-[/red] {df}")
        return

    # ---- Step 3: Parse sidebar sort keys ------------------------------------
    sidebar_map: dict[str, str] = {}
    if sidebar_config_path.exists():
        with console.status("Parsing sidebar config..."):
            sidebar_map = parse_sidebar_config(sidebar_config_path)
        console.print(f"Sidebar: [green]{len(sidebar_map)}[/green] pages mapped")
    else:
        console.print("[yellow]Sidebar config not found — using fallback sort keys[/yellow]")

    # ---- Step 4: Load / bootstrap entity dictionary -------------------------
    if entity_dict_path.exists():
        with console.status("Loading entity dictionary..."):
            api_dictionary = load_dictionary(entity_dict_path)
        console.print(f"Entity dictionary: [green]{len(api_dictionary)}[/green] entries")
    else:
        console.print(
            "[yellow]Entity dictionary not found — bootstrapping from API docs...[/yellow]"
        )
        api_dir = docs_path / "api"
        if api_dir.exists():
            with console.status("Building entity dictionary..."):
                api_dictionary = build_api_dictionary(api_dir)
                save_dictionary(api_dictionary, entity_dict_path)
            console.print(f"Built entity dictionary: [green]{len(api_dictionary)}[/green] entries")
        else:
            api_dictionary = {}
            console.print("[red]API directory not found — entity extraction disabled[/red]")

    # ---- Step 5: Parse changed markdown files → chunks ----------------------
    new_chunks: list[Chunk] = []
    failed_files: list[str] = []

    if to_process:
        console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Parsing markdown files...", total=len(to_process))
            for path in to_process:
                rel = str(path.relative_to(docs_path))
                try:
                    chunks = parse_markdown_file(path, docs_root=docs_path)
                    sort_key = compute_sort_key(rel, sidebar_map)
                    for chunk in chunks:
                        chunk.metadata.global_sort_key = sort_key
                    new_chunks.extend(chunks)
                except Exception as exc:
                    logger.exception("Failed to parse %s", rel)
                    console.print(f"  [red]Parse error in {rel}: {exc}[/red]")
                    failed_files.append(rel)
                progress.advance(task)

        console.print(
            f"Parsed [green]{len(new_chunks)}[/green] chunks "
            f"from [green]{len(to_process) - len(failed_files)}[/green] files"
            + (f" ([red]{len(failed_files)} failed[/red])" if failed_files else "")
        )

        # Warn about unusually large or small chunks
        sizes = [len(c.content) for c in new_chunks]
        large = sum(1 for s in sizes if s > 8000)
        small = sum(1 for s in sizes if s < 50)
        if large:
            console.print(
                f"  [yellow]Warning: {large} chunks > 8000 chars (may be oversized)[/yellow]"
            )
        if small:
            console.print(
                f"  [yellow]Warning: {small} chunks < 50 chars (may be undersized)[/yellow]"
            )

    # ---- Step 5b: Contextual enrichment (Gemini) for NEW chunks only --------
    page_contents: dict[str, str] = {}
    if settings.gemini_api_key and new_chunks:
        console.print()
        console.print("[bold]Contextual enrichment (Gemini)...[/bold]")

        for path in to_process:
            rel = str(path.relative_to(docs_path))
            try:
                page_contents[rel] = path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Could not read %s for enrichment: %s", rel, exc)

        gemini_client = GeminiClient(timeout=60.0)
        try:
            with console.status(f"Enriching {len(new_chunks)} chunks with contextual prefixes..."):
                enriched, skipped, errs = await enrich_chunks_contextual(
                    new_chunks,
                    page_contents,
                    gemini_client,
                )
        finally:
            await gemini_client.close()

        console.print(
            f"  Enriched: [green]{enriched}[/green], "
            f"skipped: [dim]{skipped}[/dim], "
            f"errors: [red]{errs}[/red]"
        )

        # ---- Step 5c: HyPE question generation (Gemini) for NEW chunks ------
        console.print()
        console.print("[bold]HyPE question generation (Gemini)...[/bold]")

        gemini_client_hype = GeminiClient(timeout=60.0)
        try:
            with console.status(f"Generating HyPE questions for {len(new_chunks)} chunks..."):
                hype_gen, hype_skip, hype_errs = await generate_hype_questions(
                    new_chunks,
                    page_contents,
                    gemini_client_hype,
                )
        finally:
            await gemini_client_hype.close()

        total_questions = sum(len(c.hype_questions) for c in new_chunks)
        console.print(
            f"  Generated: [green]{hype_gen}[/green] chunks, "
            f"[green]{total_questions}[/green] total questions, "
            f"skipped: [dim]{hype_skip}[/dim], "
            f"errors: [red]{hype_errs}[/red]"
        )
    elif not settings.gemini_api_key:
        console.print(
            "\n[yellow]GEMINI_API_KEY not set — skipping contextual enrichment and HyPE[/yellow]"
        )

    # ---- Step 6: Qdrant setup + load unchanged chunks + delete stale --------
    console.print()
    console.print("[bold]Setting up Qdrant...[/bold]")
    qdrant = QdrantDocClient()
    try:
        with console.status("Connecting to Qdrant..."):
            qdrant.setup_collection(recreate=False)
        console.print(f"  Collection [green]{qdrant.collection}[/green] ready")
    except Exception as exc:
        console.print(f"[red]Qdrant connection failed: {exc}[/red]")
        console.print("[red]Make sure Qdrant is running at: [/red]" + settings.qdrant_url)
        raise

    # Load unchanged leaf chunks from Qdrant for full-corpus steps
    unchanged_chunks: list[Chunk] = []
    if unchanged_files and not full:
        with console.status(f"Loading {len(unchanged_files)} unchanged files from Qdrant..."):
            unchanged_file_list = sorted(unchanged_files)
            # Fetch in batches to avoid oversized scroll requests
            for i in range(0, len(unchanged_file_list), 20):
                batch_files = unchanged_file_list[i : i + 20]
                payloads = qdrant.get_by_file_paths(
                    file_paths=batch_files,
                    chunk_types=list(_LEAF_TYPES),
                    limit=5000,
                )
                for p in payloads:
                    unchanged_chunks.append(_payload_to_chunk(p))
        console.print(
            f"  Loaded [green]{len(unchanged_chunks)}[/green] unchanged chunks from Qdrant"
        )

    # Delete stale chunks for changed + deleted files
    files_to_clean = {str(p.relative_to(docs_path)) for p in to_process} | deleted_files
    if files_to_clean:
        with console.status(f"Removing stale chunks for {len(files_to_clean)} files..."):
            for file_rel in files_to_clean:
                existing = state.get(file_rel)
                if existing and existing.chunk_ids:
                    qdrant.delete_by_file_path(file_rel)
        console.print(f"  Cleaned up [green]{len(files_to_clean)}[/green] files")

    # Remove deleted files from state
    for df in deleted_files:
        state.remove(df)

    # Delete old summary points — they'll be regenerated
    with console.status("Removing old summary points..."):
        old_summary_ids = []
        for fp in state.all_file_paths():
            fs = state.get(fp)
            if fs:
                old_summary_ids.extend(cid for cid in fs.chunk_ids if cid.endswith("#page_summary"))
        # Also find folder/top summary IDs from previous state
        # (these aren't tracked per-file, so delete by chunk_type filter)
        qdrant.delete_by_chunk_ids(old_summary_ids)
        # Delete folder + top summaries via scroll + delete
        for summary_type in ["folder_summary", "top_summary"]:
            payloads = qdrant.client.scroll(
                collection_name=qdrant.collection,
                scroll_filter=qdrant_client_filter(summary_type),
                limit=500,
                with_payload=["chunk_id"],
            )
            if payloads[0]:
                ids_to_del = [p.payload.get("chunk_id", "") for p in payloads[0]]
                if ids_to_del:
                    qdrant.delete_by_chunk_ids(ids_to_del)
    console.print("  Old summaries removed")

    # ---- Step 7: RAPTOR summaries (regenerate for affected pages) -----------
    # Build the full corpus = new + unchanged (without old summaries)
    all_leaf_chunks = new_chunks + unchanged_chunks

    summary_chunks: list[Chunk] = []
    if settings.gemini_api_key and all_leaf_chunks:
        console.print()
        console.print("[bold]Generating RAPTOR summaries (Gemini)...[/bold]")

        # For page summaries, we need page_contents for ALL pages (not just changed)
        # Load unchanged page contents from disk for summary generation
        all_page_contents = dict(page_contents)  # start with changed pages
        for fp in unchanged_files:
            full_path = docs_path / fp
            if full_path.exists() and fp not in all_page_contents:
                with contextlib.suppress(Exception):
                    all_page_contents[fp] = full_path.read_text(encoding="utf-8")

        gemini_client_summary = GeminiClient(timeout=60.0)
        try:
            # Layer 1: Page summaries for ALL pages
            with console.status("Generating page summaries..."):
                page_summaries = await generate_page_summaries(
                    all_leaf_chunks,
                    all_page_contents,
                    gemini_client_summary,
                )
            console.print(f"  Page summaries: [green]{len(page_summaries)}[/green]")

            # Layer 2: Folder summaries
            with console.status("Generating folder summaries..."):
                folder_summaries = await generate_folder_summaries(
                    page_summaries,
                    gemini_client_summary,
                )
            console.print(f"  Folder summaries: [green]{len(folder_summaries)}[/green]")

            # Layer 3: Top-level summaries
            with console.status("Generating top-level summaries..."):
                top_summaries = await generate_top_summaries(
                    folder_summaries,
                    gemini_client_summary,
                )
            console.print(f"  Top-level summaries: [green]{len(top_summaries)}[/green]")

            summary_chunks = page_summaries + folder_summaries + top_summaries
            console.print(f"  Total summaries: [green]{len(summary_chunks)}[/green]")
        finally:
            await gemini_client_summary.close()

    # Chunks to embed and upsert: new leaf chunks + all summaries
    chunks_to_index = new_chunks + summary_chunks

    if not chunks_to_index and not deleted_files:
        console.print("[yellow]No chunks to index. Exiting.[/yellow]")
        return

    # Full corpus for deterministic steps (entity, crossref, BM25)
    all_chunks = all_leaf_chunks + summary_chunks

    # ---- Step 8: Entity extraction + cross-references (full corpus) ---------
    with console.status(f"Extracting API entities from {len(all_chunks)} chunks..."):
        entity_index = build_entity_index(all_chunks, api_dictionary)
    total_entity_refs = sum(len(v) for v in entity_index.entity_to_chunks.values())
    console.print(f"Entity extraction: [green]{total_entity_refs}[/green] total entity references")

    with console.status("Extracting cross-references..."):
        crossref_graph = build_crossref_graph(all_chunks)
    total_refs = sum(len(v) for v in crossref_graph.values())
    console.print(
        f"Cross-references: [green]{total_refs}[/green] links "
        f"across [green]{len(crossref_graph)}[/green] chunks"
    )

    if not chunks_to_index:
        # Only deletions occurred — save state and exit
        state.save()
        console.print()
        console.print("[bold green]Pipeline complete (deletions only)![/bold green]")
        qdrant.close()
        return

    # ---- Step 9: Fit BM25 on full corpus ------------------------------------
    console.print()
    console.print("[bold]Fitting BM25 model...[/bold]")
    all_texts = [c.content for c in all_chunks]
    with console.status(f"Fitting BM25 on {len(all_texts)} documents..."):
        bm25_model = BM25Model()
        bm25_model.fit(all_texts)
        bm25_model.save(bm25_model_path)
    console.print(f"  BM25 vocabulary: [green]{bm25_model.vocab_size}[/green] tokens")

    # Sparse vectors only needed for chunks we're indexing
    index_texts = [c.content for c in chunks_to_index]
    with console.status(f"Computing BM25 sparse vectors for {len(index_texts)} chunks..."):
        sparse_vectors = bm25_model.get_doc_sparse_vectors(index_texts)
    console.print(f"  BM25 sparse vectors: [green]{len(sparse_vectors)}[/green]")

    # ---- Step 10: Dense embed (only new/changed chunks + summaries) ---------
    console.print()
    console.print("[bold]Embedding chunks...[/bold]")
    console.print(f"  Embedding [green]{len(chunks_to_index)}[/green] chunks via Jina (batched)")

    jina_client = JinaClient(timeout=300.0)
    try:
        with console.status("Waiting for Jina embeddings..."):
            dense_vectors, total_tokens = await embed_dense(chunks_to_index, jina_client)
    finally:
        await jina_client.close()

    console.print(f"  Embeddings received — Jina tokens used: [dim]{total_tokens:,}[/dim]")

    # ---- Step 11: Upsert to Qdrant in batches -------------------------------
    console.print()
    console.print("[bold]Upserting to Qdrant...[/bold]")
    indexed_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        upsert_task = progress.add_task("Upserting...", total=len(chunks_to_index))

        for batch_start in range(0, len(chunks_to_index), UPSERT_BATCH_SIZE):
            batch_chunks = chunks_to_index[batch_start : batch_start + UPSERT_BATCH_SIZE]
            batch_dense = dense_vectors[batch_start : batch_start + UPSERT_BATCH_SIZE]
            batch_sparse = sparse_vectors[batch_start : batch_start + UPSERT_BATCH_SIZE]

            upsert_chunks_batch(batch_chunks, batch_dense, batch_sparse, qdrant)
            indexed_count += len(batch_chunks)
            progress.advance(upsert_task, len(batch_chunks))

    console.print(f"Indexed [green]{indexed_count}[/green] chunks")

    # ---- Step 12: Embed + upsert HyPE questions (new chunks only) -----------
    hype_chunks = [c for c in new_chunks if c.hype_questions]
    if hype_chunks:
        console.print()
        console.print("[bold]Embedding HyPE questions...[/bold]")
        total_hype_q = sum(len(c.hype_questions) for c in hype_chunks)
        console.print(
            f"  Embedding [green]{total_hype_q}[/green] HyPE questions "
            f"from [green]{len(hype_chunks)}[/green] chunks"
        )

        jina_hype = JinaClient(timeout=300.0)
        try:
            with console.status("Waiting for Jina HyPE embeddings..."):
                hype_embeddings, hype_tokens = await embed_hype_questions(hype_chunks, jina_hype)
        finally:
            await jina_hype.close()

        console.print(f"  HyPE embeddings received — Jina tokens: [dim]{hype_tokens:,}[/dim]")

        # Generate BM25 sparse vectors for HyPE questions
        hype_texts = [h.question for h in hype_embeddings]
        with console.status("Computing BM25 sparse vectors for HyPE..."):
            hype_sparse = bm25_model.get_doc_sparse_vectors(hype_texts)

        # Upsert HyPE points
        console.print(f"  Upserting [green]{len(hype_embeddings)}[/green] HyPE points...")
        for batch_start in range(0, len(hype_embeddings), UPSERT_BATCH_SIZE):
            batch_hype = hype_embeddings[batch_start : batch_start + UPSERT_BATCH_SIZE]
            batch_sparse = hype_sparse[batch_start : batch_start + UPSERT_BATCH_SIZE]
            upsert_hype_batch(batch_hype, batch_sparse, qdrant)

        console.print(f"  Indexed [green]{len(hype_embeddings)}[/green] HyPE points")

    # ---- Step 13: Update state ----------------------------------------------
    now = datetime.now(UTC).isoformat()

    # Build chunk_id lists per file for new chunks + summaries
    chunks_by_file: dict[str, list[str]] = {}
    for chunk in chunks_to_index:
        fp = chunk.metadata.file_path
        if fp:  # leaf chunks and page summaries have file_path
            chunks_by_file.setdefault(fp, []).append(chunk.chunk_id)

    for path in to_process:
        if str(path.relative_to(docs_path)) in {f for f in failed_files}:
            continue
        rel = str(path.relative_to(docs_path))
        state.set(
            rel,
            FileState(
                content_hash=hash_file(path),
                pipeline_version=pipeline_version,
                chunk_ids=chunks_by_file.get(rel, []),
                last_indexed=now,
            ),
        )
    state.save()

    # ---- Summary ------------------------------------------------------------
    console.print()
    console.print("[bold green]Pipeline complete![/bold green]")
    if to_process:
        console.print(
            f"  New/changed files processed: [green]{len(to_process) - len(failed_files)}[/green]"
        )
    if deleted_files:
        console.print(f"  Deleted files cleaned up:    [red]{len(deleted_files)}[/red]")
    try:
        info = qdrant.collection_info()
        console.print(f"  Total points in Qdrant: [green]{info['points_count']}[/green]")
        console.print(f"  Collection status:      [green]{info['status']}[/green]")
    except Exception:
        pass
    qdrant.close()


def qdrant_client_filter(chunk_type: str):
    """Build a Qdrant filter for a specific chunk_type."""
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    return Filter(must=[FieldCondition(key="chunk_type", match=MatchAny(any=[chunk_type]))])
