"""A tiny MCP server for tests: tool `awards` returns the rows in the JSON file named on the command line (re-read each
call, so a test can change them); tool `drop_table` is marked destructive and must never be called."""
import json
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

path = sys.argv[1]
server = MCPServer("test-tools")


@server.tool(annotations=ToolAnnotations(read_only_hint=True), structured_output=True)
def awards(since: str = "") -> dict[str, Any]:
    return {"rows": json.load(open(path))}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
def drop_table() -> str:
    raise SystemExit("must not be called")


server.run("stdio")
