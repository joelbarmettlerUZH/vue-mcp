"""Typer CLI for the ingestion pipeline."""

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vue_docs_core.config import settings

app = typer.Typer(name="vue-docs-ingest", help="Vue docs indexing pipeline")
console = Console()


def _configure_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def run(
    docs_path: str = typer.Option(settings.vue_docs_path, help="Path to Vue docs source directory"),
    data_path: str = typer.Option(settings.data_path, help="Path to shared data directory"),
    full: bool = typer.Option(False, "--full", help="Force full re-index of all files"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without processing"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Run the ingestion pipeline: scan → parse → embed → store."""
    _configure_logging(verbose)

    docs = Path(docs_path).resolve()
    data = Path(data_path).resolve()

    if not docs.exists():
        console.print(f"[red]Docs path does not exist: {docs}[/red]")
        raise typer.Exit(1)

    from vue_docs_ingestion.pipeline import run_pipeline

    asyncio.run(
        run_pipeline(
            docs_path=docs,
            data_path=data,
            full=full,
            dry_run=dry_run,
        )
    )


@app.command()
def status(
    data_path: str = typer.Option(settings.data_path, help="Path to shared data directory"),
):
    """Show current index status."""
    from vue_docs_core.clients.qdrant import QdrantDocClient
    from vue_docs_ingestion.state import IndexState

    data = Path(data_path).resolve()
    state_path = data / "state" / "index_state.json"

    # ---- State file ---------------------------------------------------------
    if not state_path.exists():
        console.print("[yellow]No index state found. Run 'vue-docs-ingest run' first.[/yellow]")
        return

    state = IndexState(state_path)
    all_files = state.all_file_paths()

    if not all_files:
        console.print("[yellow]Index state is empty.[/yellow]")
        return

    # Aggregate stats
    total_chunks = 0
    by_folder: dict[str, int] = {}
    last_indexed_times: list[str] = []

    for file_path in all_files:
        fs = state.get(file_path)
        if fs is None:
            continue
        n = len(fs.chunk_ids)
        total_chunks += n
        folder = file_path.split("/")[0] if "/" in file_path else file_path
        by_folder[folder] = by_folder.get(folder, 0) + n
        if fs.last_indexed:
            last_indexed_times.append(fs.last_indexed)

    last_run = max(last_indexed_times) if last_indexed_times else "unknown"

    console.print(f"\n[bold]Index State[/bold] — {state_path}")
    console.print(f"  Indexed files:  [green]{len(all_files)}[/green]")
    console.print(f"  Total chunks:   [green]{total_chunks}[/green]")
    console.print(f"  Last indexed:   [dim]{last_run}[/dim]")

    # Per-folder table
    if by_folder:
        console.print()
        table = Table(title="Chunks by top-level folder", show_header=True)
        table.add_column("Folder", style="cyan")
        table.add_column("Chunks", justify="right", style="green")
        for folder, count in sorted(by_folder.items()):
            table.add_row(folder, str(count))
        console.print(table)

    # ---- Qdrant live stats --------------------------------------------------
    console.print()
    console.print("[bold]Qdrant[/bold] —", settings.qdrant_url)
    try:
        qdrant = QdrantDocClient()
        info = qdrant.collection_info()
        console.print(f"  Collection:   [green]{qdrant.collection}[/green]")
        console.print(f"  Points count: [green]{info['points_count']}[/green]")
        console.print(f"  Status:       [green]{info['status']}[/green]")
        qdrant.close()
    except Exception as exc:
        console.print(f"  [red]Could not connect: {exc}[/red]")


if __name__ == "__main__":
    app()
