#!/usr/bin/env python3
"""Debug utility: show chunks for a given doc page.

Usage:
    uv run python scripts/inspect_chunks.py guide/essentials/computed.md
    uv run python scripts/inspect_chunks.py guide/essentials/lifecycle.md
"""

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vue_docs_core.models.chunk import ChunkType
from vue_docs_core.parsing.markdown import parse_markdown_file

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "vue-docs" / "src"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/inspect_chunks.py <relative_path>")
        print("Example: uv run python scripts/inspect_chunks.py guide/essentials/computed.md")
        sys.exit(1)

    rel_path = sys.argv[1]
    file_path = DOCS_ROOT / rel_path
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    console = Console()
    chunks = parse_markdown_file(file_path, DOCS_ROOT)

    console.print(f"\n[bold]Parsed {len(chunks)} chunks from {rel_path}[/bold]\n")

    # --- summary table ---
    type_counts: dict[str, int] = {}
    for c in chunks:
        type_counts[c.chunk_type.value] = type_counts.get(c.chunk_type.value, 0) + 1
    for ctype, count in sorted(type_counts.items()):
        console.print(f"  {ctype}: {count}")
    console.print()

    table = Table(title="Chunk Summary")
    table.add_column("ID", style="cyan", max_width=55)
    table.add_column("Type", style="green", width=12)
    table.add_column("Style", style="yellow", width=12)
    table.add_column("Content preview", max_width=60)

    for chunk in chunks:
        preview = chunk.content[:80].replace("\n", " ")
        table.add_row(
            chunk.chunk_id,
            chunk.chunk_type.value,
            chunk.metadata.api_style,
            preview,
        )
    console.print(table)

    # --- detailed panels ---
    if "--detail" not in sys.argv:
        console.print("\n[dim]Pass --detail for full chunk panels[/dim]\n")
        return

    for chunk in chunks:
        title = f"[{chunk.chunk_type.value}] {chunk.chunk_id}"
        subtitle = f"api_style={chunk.metadata.api_style} | breadcrumb={chunk.metadata.breadcrumb}"

        if chunk.chunk_type == ChunkType.CODE_BLOCK:
            body = f"Language: {chunk.metadata.language_tag}\n"
            if chunk.metadata.preceding_prose:
                prose_preview = chunk.metadata.preceding_prose[:120]
                body += f"Preceding prose: {prose_preview}...\n\n"
            body += chunk.content[:500]
        elif chunk.chunk_type == ChunkType.IMAGE:
            body = f"Image: {chunk.content}\n"
            if chunk.metadata.preceding_prose:
                body += f"Context: {chunk.metadata.preceding_prose[:200]}"
        else:
            body = chunk.content[:500]
            if len(chunk.content) > 500:
                body += f"\n... ({len(chunk.content)} total chars)"

        extras: list[str] = []
        if chunk.metadata.child_chunk_ids:
            extras.append(f"Children: {chunk.metadata.child_chunk_ids}")
        if chunk.metadata.parent_chunk_id:
            extras.append(f"Parent: {chunk.metadata.parent_chunk_id}")
        if chunk.metadata.sibling_chunk_ids:
            extras.append(f"Siblings: {chunk.metadata.sibling_chunk_ids}")
        if extras:
            body += "\n\n" + "\n".join(extras)

        console.print(Panel(body, title=title, subtitle=subtitle))


if __name__ == "__main__":
    main()
