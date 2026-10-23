"""Shared pieces for framework-parameterised tools and prompts."""

from typing import Annotated, Literal

from pydantic import Field

from vue_docs_core.data.sources import SourceDefinition


def framework_param(sources: list[SourceDefinition]):
    """Annotated type for a required ``framework`` argument, rendered as an enum in the schema."""
    names = tuple(s.name for s in sources)
    listing = ", ".join(f"'{s.name}' ({s.display_name})" for s in sources)
    return Annotated[
        Literal[names],
        Field(description=f"Documentation source to query: {listing}."),
    ]


def tool_ref(tool: str, source: str | None) -> str:
    """Markdown reference to a tool, pinned to a framework when one is given.

    Without a source only ``ecosystem_search`` is meaningful, so every tool maps to it.
    """
    if source is None:
        return "`ecosystem_search`"
    return f'`{tool}` (framework `"{source}"`)'
