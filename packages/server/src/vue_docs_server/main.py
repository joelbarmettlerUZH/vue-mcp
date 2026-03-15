"""FastMCP app setup, tool registration, and startup hooks."""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from vue_docs_server.startup import startup, shutdown
from vue_docs_server.tools.search import vue_docs_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Server lifespan: startup and shutdown hooks."""
    startup()
    logger.info("MCP server ready")
    yield
    shutdown()


mcp = FastMCP(
    "Vue Docs MCP Server",
    instructions=(
        "This server provides search access to the Vue.js documentation. "
        "Use vue_docs_search to find documentation about Vue concepts, APIs, "
        "components, directives, and patterns. You can scope searches to "
        "specific documentation sections like 'guide', 'api', or 'tutorial'."
    ),
    lifespan=lifespan,
)


@mcp.tool()
async def vue_docs_search_tool(
    query: str,
    scope: str = "all",
    max_results: int = 10,
) -> str:
    """Search the Vue.js documentation for answers to developer questions.

    Returns reconstructed documentation fragments with code examples,
    breadcrumb navigation paths, and source URLs — ordered by the
    documentation's natural reading flow.

    Args:
        query: A developer question or topic to search for. Examples:
               "how does computed caching work",
               "v-model on custom components",
               "defineProps TypeScript usage".
        scope: Documentation section to search. Use "all" (default) for
               full documentation, or narrow with: "guide", "guide/essentials",
               "guide/components", "api", "tutorial", "examples".
        max_results: Number of documentation sections to return (1-20, default 10).
    """
    return await vue_docs_search(query=query, scope=scope, max_results=max_results)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
