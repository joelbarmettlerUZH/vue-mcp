"""Full pipeline: scan → parse → enrich → embed → store."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.jina import JinaClient
from vue_docs_core.clients.qdrant import QdrantDocClient
from vue_docs_core.config import settings
from vue_docs_core.models.chunk import Chunk
from vue_docs_core.parsing.crossrefs import build_crossref_graph
from vue_docs_core.parsing.entities import (
    build_api_dictionary,
    build_entity_index,
    load_dictionary,
    save_dictionary,
)
from vue_docs_core.parsing.markdown import parse_markdown_file
from vue_docs_core.parsing.sort_keys import compute_sort_key, parse_sidebar_config
from vue_docs_ingestion.embedder import embed_dense_batched
from vue_docs_ingestion.indexer import upsert_chunks_batch
from vue_docs_ingestion.scanner import find_markdown_files, hash_file
from vue_docs_ingestion.state import FileState, IndexState

logger = logging.getLogger(__name__)
console = Console()

# How many chunks to embed + upsert per outer loop iteration
_UPSERT_BATCH = 256


async def run_pipeline(
    docs_path: Path,
    data_path: Path,
    *,
    full: bool = False,
    dry_run: bool = False,
    embed_batch_size: int = 32,
) -> None:
    """Run the full ingestion pipeline.

    Stages (Day 5 MVP — no enrichment, HyPE, or summaries):
      1. Discover markdown files
      2. Detect which files need re-processing
      3. Parse .md → Chunk objects
      4. Extract API entities
      5. Extract cross-references
      6. Assign sort keys
      7. Fit BM25 on corpus
      8. Embed with Jina (dense) + BM25 (sparse)
      9. Upsert to Qdrant
     10. Persist state

    Args:
        docs_path: Path to Vue docs source (e.g. ./data/vue-docs/src).
        data_path: Path to shared data directory.
        full: Force full re-index even for unchanged files.
        dry_run: Show what would be processed without making changes.
        embed_batch_size: Chunks per Jina embedding API call.
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

    # ---- Step 1: Discover files ---------------------------------------------
    with console.status("Discovering markdown files..."):
        md_files = find_markdown_files(docs_path)
    console.print(f"Found [green]{len(md_files)}[/green] markdown files")

    # ---- Step 2: Change detection -------------------------------------------
    state = IndexState(state_path)

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

    up_to_date_count = len(md_files) - len(to_process)
    console.print(
        f"Files to process: [green]{len(to_process)}[/green], "
        f"up-to-date: [dim]{up_to_date_count}[/dim]"
    )

    if not to_process:
        console.print("[green]Everything up-to-date. Nothing to do.[/green]")
        return

    if dry_run:
        console.print("\n[yellow]Files that would be processed:[/yellow]")
        for p in to_process:
            console.print(f"  {p.relative_to(docs_path)}")
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
        console.print("[yellow]Entity dictionary not found — bootstrapping from API docs...[/yellow]")
        api_dir = docs_path / "api"
        if api_dir.exists():
            with console.status("Building entity dictionary..."):
                api_dictionary = build_api_dictionary(api_dir)
                save_dictionary(api_dictionary, entity_dict_path)
            console.print(
                f"Built entity dictionary: [green]{len(api_dictionary)}[/green] entries"
            )
        else:
            api_dictionary = {}
            console.print("[red]API directory not found — entity extraction disabled[/red]")

    # ---- Step 5: Parse markdown files → chunks ------------------------------
    console.print()
    all_chunks: list[Chunk] = []
    failed_files: list[str] = []

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
                all_chunks.extend(chunks)
            except Exception as exc:
                logger.exception("Failed to parse %s", rel)
                console.print(f"  [red]Parse error in {rel}: {exc}[/red]")
                failed_files.append(rel)
            progress.advance(task)

    console.print(
        f"Parsed [green]{len(all_chunks)}[/green] chunks "
        f"from [green]{len(to_process) - len(failed_files)}[/green] files"
        + (f" ([red]{len(failed_files)} failed[/red])" if failed_files else "")
    )

    if not all_chunks:
        console.print("[yellow]No chunks to index. Exiting.[/yellow]")
        return

    # Warn about unusually large or small chunks
    sizes = [len(c.content) for c in all_chunks]
    large = sum(1 for s in sizes if s > 8000)
    small = sum(1 for s in sizes if s < 50)
    if large:
        console.print(f"  [yellow]Warning: {large} chunks > 8000 chars (may be oversized)[/yellow]")
    if small:
        console.print(f"  [yellow]Warning: {small} chunks < 50 chars (may be undersized)[/yellow]")

    # ---- Step 6: Entity extraction ------------------------------------------
    with console.status(f"Extracting API entities from {len(all_chunks)} chunks..."):
        entity_index = build_entity_index(all_chunks, api_dictionary)
    total_entity_refs = sum(len(v) for v in entity_index.entity_to_chunks.values())
    console.print(f"Entity extraction: [green]{total_entity_refs}[/green] total entity references")

    # ---- Step 7: Cross-reference extraction ---------------------------------
    with console.status("Extracting cross-references..."):
        crossref_graph = build_crossref_graph(all_chunks)
    total_refs = sum(len(v) for v in crossref_graph.values())
    console.print(
        f"Cross-references: [green]{total_refs}[/green] links "
        f"across [green]{len(crossref_graph)}[/green] chunks"
    )

    # ---- Step 8: Qdrant setup + cleanup -------------------------------------
    console.print()
    console.print("[bold]Setting up Qdrant...[/bold]")
    qdrant = QdrantDocClient()
    try:
        with console.status("Connecting to Qdrant..."):
            qdrant.setup_collection(recreate=False)
        console.print(f"  Collection [green]{qdrant.collection}[/green] ready")

        # Delete stale chunks for files being re-indexed
        files_to_reindex = {str(p.relative_to(docs_path)) for p in to_process}
        with console.status("Removing stale chunks for changed files..."):
            for file_rel in files_to_reindex:
                existing = state.get(file_rel)
                if existing and existing.chunk_ids:
                    qdrant.delete_by_file_path(file_rel)
    except Exception as exc:
        console.print(f"[red]Qdrant connection failed: {exc}[/red]")
        console.print("[red]Make sure Qdrant is running at: [/red]" + settings.qdrant_url)
        raise

    # ---- Step 9: Fit BM25 ---------------------------------------------------
    console.print()
    console.print("[bold]Fitting BM25 model...[/bold]")
    texts = [c.content for c in all_chunks]
    with console.status(f"Fitting BM25 on {len(texts)} documents..."):
        bm25_model = BM25Model()
        bm25_model.fit(texts)
        bm25_model.save(bm25_model_path)
    console.print(f"  BM25 vocabulary: [green]{bm25_model.vocab_size}[/green] tokens")

    # Pre-compute all sparse vectors (must be done on fitted corpus in order)
    with console.status("Computing BM25 sparse vectors..."):
        all_sparse_vectors = bm25_model.get_doc_sparse_vectors(texts)
    console.print(f"  BM25 sparse vectors: [green]{len(all_sparse_vectors)}[/green]")

    # ---- Step 10: Dense embed + upsert --------------------------------------
    console.print()
    console.print("[bold]Embedding and indexing chunks...[/bold]")

    jina_client = JinaClient()
    total_tokens = 0
    indexed_count = 0

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            embed_task = progress.add_task(
                "Embedding + upserting...", total=len(all_chunks)
            )

            for batch_start in range(0, len(all_chunks), _UPSERT_BATCH):
                batch_chunks = all_chunks[batch_start : batch_start + _UPSERT_BATCH]
                batch_sparse = all_sparse_vectors[batch_start : batch_start + _UPSERT_BATCH]

                dense_vectors, tokens = await embed_dense_batched(
                    batch_chunks, jina_client, batch_size=embed_batch_size
                )
                total_tokens += tokens

                upsert_chunks_batch(batch_chunks, dense_vectors, batch_sparse, qdrant)
                indexed_count += len(batch_chunks)
                progress.advance(embed_task, len(batch_chunks))

    finally:
        await jina_client.close()

    console.print(
        f"Indexed [green]{indexed_count}[/green] chunks "
        f"(Jina tokens used: [dim]{total_tokens:,}[/dim])"
    )

    # ---- Step 11: Update state ----------------------------------------------
    now = datetime.now(timezone.utc).isoformat()
    chunks_by_file: dict[str, list[str]] = {}
    for chunk in all_chunks:
        chunks_by_file.setdefault(chunk.metadata.file_path, []).append(chunk.chunk_id)

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
    try:
        info = qdrant.collection_info()
        console.print(f"  Total points in Qdrant: [green]{info['points_count']}[/green]")
        console.print(f"  Collection status:      [green]{info['status']}[/green]")
    except Exception:
        pass
    qdrant.close()
