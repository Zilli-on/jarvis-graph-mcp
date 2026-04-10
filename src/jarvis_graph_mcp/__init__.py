"""jarvis-graph-mcp — Local-first code intelligence MCP server.

Wraps jarvis-graph-lite's 17 commands as Model Context Protocol tools
so any MCP-compatible client (Claude Desktop, Claude Code, Cursor,
Windsurf, Cline, ...) can ask questions like "what are the top
refactor priorities in this repo?" and get a structured answer
without uploading any source code to the cloud.

Design:
  - No telemetry, no network calls besides the MCP client <-> server
    stdio channel.
  - The heavy lifting happens inside the bundled jarvis-graph-lite
    package, which is itself pure stdlib.
  - Each MCP tool is a thin wrapper that shells out to
    `python -m jarvis_graph <command> --json` and returns the parsed
    payload to the caller.
"""

__version__ = "0.1.0"
