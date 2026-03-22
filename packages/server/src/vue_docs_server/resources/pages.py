"""Page content resource — raw markdown of a documentation page, per-source."""

from fastmcp.exceptions import ResourceError

from vue_docs_core.data.sources import SourceDefinition
from vue_docs_server.startup import state
from vue_docs_server.usage import log_resource_read


async def _do_read_page(path: str, source: str) -> str:
    """Shared page read implementation."""
    if state.db:
        content = state.db.read_page(path, source=source)
        if content is None:
            page_paths = state.page_paths_by_source.get(source, [])
            available = ", ".join(p.removesuffix(".md") for p in page_paths[:10])
            raise ResourceError(
                f"Page not found: {path}. Read {source}://topics for available pages. "
                f"Examples: {available}"
            )
        log_resource_read(f"{source}://pages/{path}", framework=source, response_chars=len(content))
        return content

    raise ResourceError(
        f"Page content not available. Database not configured for source '{source}'."
    )


def make_page_resource(source_def: SourceDefinition):
    """Create a source-specific page resource function."""
    source_name = source_def.name
    display = source_def.display_name

    async def doc_page(path: str) -> str:
        return await _do_read_page(path, source=source_name)

    doc_page.__name__ = f"{source_name}_doc_page"
    doc_page.__doc__ = f"Return the raw markdown content of a {display} documentation page."
    return doc_page
