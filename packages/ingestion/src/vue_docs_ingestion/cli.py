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
from vue_docs_core.data.sources import SOURCE_REGISTRY, SourceDefinition, get_enabled_sources
from vue_docs_core.parsing.adapters import get_adapter

app = typer.Typer(name="vue-docs-ingest", help="Vue ecosystem docs indexing pipeline")
console = Console()


def _configure_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    # Suppress noisy third-party loggers even in verbose mode
    for name in ("markdown_it", "httpcore", "httpx", "hpack"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _get_db():
    """Create a PostgresClient. Requires DATABASE_URL."""
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Set it in .env or as an environment variable."
        )
    from vue_docs_core.clients.postgres import PostgresClient

    db = PostgresClient(settings.database_url)
    db.create_tables()
    return db


def _resolve_docs_path(source_def: SourceDefinition, base_data_path: Path) -> Path:
    """Resolve the docs path for a source within the data directory."""
    return base_data_path / f"{source_def.name}-docs" / source_def.docs_subpath


def _clone_or_pull(source_def: SourceDefinition, base_data_path: Path) -> Path:
    """Clone or pull the docs repo for a source. Returns the docs path."""
    repo_dir = base_data_path / f"{source_def.name}-docs"
    docs_path = repo_dir / source_def.docs_subpath

    if (repo_dir / ".git").exists():
        console.print(f"[bold]Pulling latest {source_def.display_name} docs...[/bold]")
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "pull"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"  {result.stdout.strip()}")
        else:
            console.print(f"  [yellow]git pull warning: {result.stderr.strip()}[/yellow]")
    else:
        console.print(f"[bold]Cloning {source_def.display_name} docs...[/bold]")
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                source_def.git_url,
                str(repo_dir),
            ],
            check=True,
        )

    # Run adapter post-clone hook (e.g. TypeDoc generation)
    adapter = get_adapter(source_def.name)
    with console.status(f"Running post-clone setup for {source_def.display_name}..."):
        adapter.post_clone(repo_dir)

    return docs_path


@app.command()
def run(
    source: str = typer.Option(
        "",
        "--source",
        "-s",
        help=f"Source to ingest (default: all enabled). Available: {', '.join(SOURCE_REGISTRY)}",
    ),
    docs_path: str = typer.Option("", help="Override docs source directory path"),
    data_path: str = typer.Option(settings.data_path, help="Path to shared data directory"),
    full: bool = typer.Option(False, "--full", help="Force full re-index of all files"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without processing"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Run the ingestion pipeline: scan -> parse -> embed -> store."""
    _configure_logging(verbose)

    data = Path(data_path).resolve()

    # Determine which sources to process
    if source:
        sources = get_enabled_sources(source)
    else:
        sources = get_enabled_sources(settings.enabled_sources)

    from vue_docs_ingestion.pipeline import run_pipeline

    for source_def in sources:
        if docs_path:
            docs = Path(docs_path).resolve()
        else:
            docs = _resolve_docs_path(source_def, data)

        if not docs.exists():
            console.print(
                f"[yellow]Docs path does not exist for {source_def.display_name}: {docs}[/yellow]"
            )
            console.print("[dim]Trying to clone...[/dim]")
            docs = _clone_or_pull(source_def, data)

        if not docs.exists():
            console.print(f"[red]Docs path still does not exist: {docs}[/red]")
            continue

        db = _get_db()
        try:
            asyncio.run(
                run_pipeline(
                    docs_path=docs,
                    data_path=data,
                    full=full,
                    dry_run=dry_run,
                    db=db,
                    source=source_def,
                )
            )
        finally:
            db.close()

        console.print()


@app.command()
def watch(
    interval_hours: int = typer.Option(24, help="Hours between ingestion runs"),
    data_path: str = typer.Option(settings.data_path, help="Path to shared data directory"),
    full: bool = typer.Option(False, "--full", help="Force full re-index on first run"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Run ingestion on a repeating schedule. Pulls latest docs before each run."""
    _configure_logging(verbose)

    data = Path(data_path).resolve()
    sources = get_enabled_sources(settings.enabled_sources)

    from vue_docs_ingestion.pipeline import run_pipeline

    logger = logging.getLogger(__name__)
    first_run = True
    consecutive_failures: dict[str, int] = {}
    max_consecutive_failures = 5

    while True:
        for source_def in sources:
            console.print(f"\n[bold blue]Processing {source_def.display_name}...[/bold blue]")

            # Clone or pull
            docs = _clone_or_pull(source_def, data)

            if not docs.exists():
                console.print(f"[red]Docs source not found at {docs} after clone/pull[/red]")
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
                        source=source_def,
                    )
                )
                consecutive_failures[source_def.name] = 0
            except Exception:
                logger.exception("Ingestion pipeline failed for %s", source_def.name)
                consecutive_failures[source_def.name] = (
                    consecutive_failures.get(source_def.name, 0) + 1
                )
                count = consecutive_failures[source_def.name]
                console.print(
                    f"[red]Pipeline failed for {source_def.display_name} "
                    f"({count}/{max_consecutive_failures} consecutive failures). "
                    "Will retry next cycle.[/red]"
                )
                if count >= max_consecutive_failures:
                    raise RuntimeError(
                        f"Pipeline for {source_def.name} failed "
                        f"{max_consecutive_failures} consecutive times"
                    ) from None
            finally:
                db.close()

        first_run = False
        console.print(f"\n[dim]Next ingestion in {interval_hours} hours...[/dim]\n")
        time.sleep(interval_hours * 3600)


@app.command()
def status():
    """Show current index status for all sources."""
    from vue_docs_core.clients.qdrant import QdrantDocClient
    from vue_docs_ingestion.state import IndexState

    db = _get_db()
    sources = get_enabled_sources(settings.enabled_sources)

    for source_def in sources:
        console.print(f"\n[bold]{source_def.display_name}[/bold]")

        state = IndexState(db=db, source=source_def.name)

        all_files = state.all_file_paths()

        if not all_files:
            console.print("  [yellow]Index state is empty.[/yellow]")
            continue

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

        console.print(f"  Indexed files:  [green]{len(all_files)}[/green]")
        console.print(f"  Total chunks:   [green]{total_chunks}[/green]")
        console.print(f"  Last indexed:   [dim]{last_run}[/dim]")

        if by_folder:
            table = Table(show_header=True)
            table.add_column("Folder", style="cyan")
            table.add_column("Chunks", justify="right", style="green")
            for folder, count in sorted(by_folder.items()):
                table.add_row(folder, str(count))
            console.print(table)

    # ---- Qdrant live stats --------------------------------------------------
    console.print()
    console.print("[bold]Qdrant[/bold] —", settings.qdrant_url)
    qdrant = QdrantDocClient()
    info = qdrant.collection_info()
    console.print(f"  Collection:   [green]{qdrant.collection}[/green]")
    console.print(f"  Points count: [green]{info['points_count']}[/green]")
    console.print(f"  Status:       [green]{info['status']}[/green]")
    qdrant.close()

    db.close()


if __name__ == "__main__":
    app()
