"""Page content resource — raw markdown of any Vue.js documentation page."""

from fastmcp.exceptions import ResourceError

from vue_docs_server.startup import state


async def vue_doc_page(path: str) -> str:
    """Return the raw markdown content of a Vue.js documentation page."""
    if state.vue_docs_path is None:
        raise ResourceError("Server not initialized.")

    md_path = state.vue_docs_path / f"{path}.md"
    if not md_path.exists():
        available = ", ".join(p.removesuffix(".md") for p in state.page_paths[:10])
        raise ResourceError(
            f"Page not found: {path}. Read vue://topics for available pages. Examples: {available}"
        )

    return md_path.read_text(encoding="utf-8")
