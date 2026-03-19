"""Typer CLI for the ingestion pipeline."""

import asyncio
import logging
import subprocess
import time
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


def _get_db():
    """Create a PostgresClient if DATABASE_URL is configured."""
    if not settings.database_url:
        return None
    from vue_docs_core.clients.postgres import PostgresClient

    db = PostgresClient(settings.database_url)
    db.create_tables()
    return db


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

    db = _get_db()
    try:
        asyncio.run(
            run_pipeline(
                docs_path=docs,
                data_path=data,
                full=full,
                dry_run=dry_run,
                db=db,
            )
        )
    finally:
        if db:
            db.close()


@app.command()
def watch(
    interval_hours: int = typer.Option(24, help="Hours between ingestion runs"),
    docs_path: str = typer.Option(settings.vue_docs_path, help="Path to Vue docs source directory"),
    data_path: str = typer.Option(settings.data_path, help="Path to shared data directory"),
    full: bool = typer.Option(False, "--full", help="Force full re-index on first run"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Run ingestion on a repeating schedule. Pulls latest Vue docs before each run."""
    _configure_logging(verbose)

    docs = Path(docs_path).resolve()
    data = Path(data_path).resolve()
    docs_repo = docs.parent  # vue-docs root (parent of src/)

    from vue_docs_ingestion.pipeline import run_pipeline

    logger = logging.getLogger(__name__)
    first_run = True

    while True:
        # Pull latest Vue docs (or clone if first time)
        if (docs_repo / ".git").exists():
            console.print("[bold]Pulling latest Vue docs...[/bold]")
            result = subprocess.run(
                ["git", "-C", str(docs_repo), "pull"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print(f"  {result.stdout.strip()}")
            else:
                console.print(f"  [yellow]git pull warning: {result.stderr.strip()}[/yellow]")
        else:
            console.print("[bold]Cloning Vue docs...[/bold]")
            docs_repo.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "https://github.com/vuejs/docs.git",
                    str(docs_repo),
                ],
                check=True,
            )

        if not docs.exists():
            console.print(f"[red]Docs source not found at {docs} after clone/pull[/red]")
            console.print(f"[dim]Retrying in {interval_hours} hours...[/dim]")
            time.sleep(interval_hours * 3600)
            continue

        # Run pipeline
        db = _get_db()
        try:
            asyncio.run(
                run_pipeline(
                    docs_path=docs,
                    data_path=data,
                    full=full if first_run else False,
                    db=db,
                )
            )
        except Exception:
            logger.exception("Ingestion pipeline failed")
            console.print("[red]Pipeline failed — see logs above. Will retry next cycle.[/red]")
        finally:
            if db:
                db.close()

        first_run = False
        console.print(f"\n[dim]Next ingestion in {interval_hours} hours...[/dim]\n")
        time.sleep(interval_hours * 3600)


@app.command()
def status(
    data_path: str = typer.Option(settings.data_path, help="Path to shared data directory"),
):
    """Show current index status."""
    from vue_docs_core.clients.qdrant import QdrantDocClient
    from vue_docs_ingestion.state import IndexState

    data = Path(data_path).resolve()

    # Try PG first, fall back to file
    db = _get_db()
    if db:
        state = IndexState(db=db)
    else:
        state_path = data / "state" / "index_state.json"
        if not state_path.exists():
            console.print("[yellow]No index state found. Run 'vue-docs-ingest run' first.[/yellow]")
            return
        state = IndexState(state_path=state_path)

    all_files = state.all_file_paths()

    if not all_files:
        console.print("[yellow]Index state is empty.[/yellow]")
        if db:
            db.close()
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

    source = "PostgreSQL" if db else f"{data / 'state' / 'index_state.json'}"
    console.print(f"\n[bold]Index State[/bold] — {source}")
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

    if db:
        db.close()


if __name__ == "__main__":
    app()
