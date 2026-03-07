"""FastMCP app setup, tool registration, and startup hooks."""

from fastmcp import FastMCP

mcp = FastMCP("Vue Docs MCP Server")


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
