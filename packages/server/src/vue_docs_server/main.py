"""FastMCP app setup, tool/resource/prompt registration, and startup hooks."""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from vue_docs_server.prompts import compare_vue_apis, debug_vue_issue, migrate_vue_pattern
from vue_docs_server.resources.api_index import vue_api_entity, vue_api_index
from vue_docs_server.resources.pages import vue_doc_page
from vue_docs_server.resources.scopes import vue_search_scopes
from vue_docs_server.resources.topics import vue_section_topics, vue_table_of_contents
from vue_docs_server.startup import shutdown, startup
from vue_docs_server.tools.api_lookup import vue_api_lookup
from vue_docs_server.tools.related import vue_get_related
from vue_docs_server.tools.search import vue_docs_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
This server provides comprehensive access to the Vue.js documentation.

**Resources** (browse without searching):
- `vue://topics` — Full table of contents with all pages and sections
- `vue://topics/{section}` — TOC for a specific section (e.g., `vue://topics/guide/essentials`)
- `vue://pages/{path}` — Raw markdown of any doc page (e.g., `vue://pages/guide/essentials/computed`)
- `vue://api/index` — Complete API entity index grouped by type
- `vue://api/entities/{name}` — Details for a specific API (e.g., `vue://api/entities/ref`)
- `vue://scopes` — Valid scope values for narrowing searches

**Tools** (for active retrieval):
- `vue_docs_search` — Semantic search across the full documentation
- `vue_api_lookup` — Fast exact-match API reference lookup
- `vue_get_related` — Find related APIs, concepts, and documentation pages

**Prompts** (structured workflows):
- `debug_vue_issue` — Systematic Vue.js debugging workflow
- `compare_vue_apis` — Side-by-side API/pattern comparison
- `migrate_vue_pattern` — Migration guide between patterns

Start by reading `vue://topics` to understand the documentation structure, \
then use `vue_docs_search` for specific questions.\
"""


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Server lifespan: startup and shutdown hooks."""
    startup()
    logger.info("MCP server ready")
    yield
    shutdown()


mcp = FastMCP(
    "Vue Docs MCP Server",
    instructions=INSTRUCTIONS,
    lifespan=lifespan,
)

# Tools
mcp.tool(annotations={"readOnlyHint": True})(vue_docs_search)
mcp.tool(annotations={"readOnlyHint": True})(vue_api_lookup)
mcp.tool(annotations={"readOnlyHint": True})(vue_get_related)

# Resources
mcp.resource("vue://pages/{path*}", mime_type="text/markdown")(vue_doc_page)
mcp.resource("vue://topics", mime_type="text/markdown")(vue_table_of_contents)
mcp.resource("vue://topics/{section*}", mime_type="text/markdown")(vue_section_topics)
mcp.resource("vue://api/index", mime_type="text/markdown")(vue_api_index)
mcp.resource("vue://api/entities/{name}", mime_type="text/markdown")(vue_api_entity)
mcp.resource("vue://scopes", mime_type="text/markdown")(vue_search_scopes)

# Prompts
mcp.prompt(debug_vue_issue)
mcp.prompt(compare_vue_apis)
mcp.prompt(migrate_vue_pattern)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
