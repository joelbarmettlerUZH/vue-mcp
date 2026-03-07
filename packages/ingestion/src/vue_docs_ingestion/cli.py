"""Typer CLI for the ingestion pipeline."""

import typer

app = typer.Typer(name="vue-docs-ingest", help="Vue docs indexing pipeline")


@app.command()
def run(
    docs_path: str = typer.Option("./data/vue-docs/src", help="Path to Vue docs source"),
    full: bool = typer.Option(False, help="Force full re-index"),
    dry_run: bool = typer.Option(False, help="Show what would change without processing"),
) -> None:
    """Run the ingestion pipeline."""
    typer.echo(f"Ingestion pipeline: docs_path={docs_path}, full={full}, dry_run={dry_run}")
    typer.echo("Not yet implemented.")


@app.command()
def status() -> None:
    """Show current index status."""
    typer.echo("Index status: not yet implemented.")


if __name__ == "__main__":
    app()
