# jarvis-graph-mcp

**Local-first code intelligence MCP server for Python projects.**
Works with Claude Desktop, Claude Code, Cursor, Windsurf, Cline, and
any other [Model Context Protocol](https://modelcontextprotocol.io)
client. No telemetry. No cloud. No API costs. Your source never
leaves your machine.

---

## What it does

Exposes **18 code-intelligence tools** to any MCP client so your LLM
assistant can ask structural questions about your codebase and get
structured answers — not fuzzy grep results.

| Tool | Answers |
|---|---|
| `refactor_priority` | "What are the top 10 things to refactor right now?" |
| `find_coverage_gaps` | "Which public symbols have zero tests reaching them?" |
| `generate_test_skeleton` | "Give me a starter unittest file for this symbol" |
| `health_report` | "Give me a one-shot overview of this repo's debt" |
| `detect_changes` | "What changed since my last scan?" |
| `summary` | "File count, symbol count, complexity — deterministic" |
| `query` | "Where is `validate_upload` defined?" |
| `context` | "Who calls `beat_match_edit` and what does it call?" |
| `impact` | "If I change this function, what breaks?" |
| `find_path` | "How does `main()` eventually reach `render_amv()`?" |
| `find_dead_code` | "What's never called anywhere?" |
| `find_unused_imports` | "What can I delete from my import blocks?" |
| `find_circular_deps` | "Do I have any import cycles?" |
| `find_complexity` | "What's over cyclomatic 10?" |
| `find_long_functions` | "What's over 50 lines?" |
| `find_god_files` | "Which files carry too much responsibility?" |
| `find_high_fan_out` | "Which files couple too tightly to the rest?" |
| `find_todo_comments` | "Which TODOs are actually high-risk vs noise?" |

Every tool is a wrapper around
[jarvis-graph-lite](https://github.com/Zilli-on/jarvis-graph-lite)
(bundled separately), a stdlib-only code index with **273 passing
tests**.

## Why local-first

- **Privacy**: your source never uploads anywhere. The only network
  traffic is the MCP stdio channel between your editor and this
  server, both on localhost.
- **Cost**: runs inside the Python interpreter you already have. No
  per-call API fee, no per-seat subscription, no monthly tool usage
  cap.
- **Speed**: no round-trip to a hosted API. Queries hit an on-disk
  index that rebuilds only the files you actually changed.
- **Offline**: works on a plane. Works on a train. Works in a SCIF.

## Installation

### Requirements

- Python 3.10+
- The `mcp` Python package (`pip install mcp`)
- A clone of [jarvis-graph-lite](https://github.com/Zilli-on/jarvis-graph-lite)
  somewhere on disk

### Install this package

```bash
pip install jarvis-graph-mcp
```

Or, from a local checkout:

```bash
git clone https://github.com/Zilli-on/jarvis-graph-mcp.git
cd jarvis-graph-mcp
pip install -e .
```

### Point it at jarvis-graph-lite

The MCP server needs to know where the lite package lives. Two
options:

1. **Environment variable** (recommended):
   ```
   set JARVIS_GRAPH_LITE_PATH=C:\path\to\jarvis-graph-lite\src
   ```
2. **Sibling checkout**: clone `jarvis-graph-lite` next to this repo
   so the directory structure is
   `.../some-parent/jarvis-graph-lite/src/` and
   `.../some-parent/jarvis-graph-mcp/`. The server auto-discovers it.

3. **Windows default**: if you have
   `C:\JARVIS\tools\jarvis-graph-lite\src\` on disk, the server finds
   it without any config.

## Client setup

### Claude Desktop

Edit your `claude_desktop_config.json`
(`%APPDATA%\Claude\claude_desktop_config.json` on Windows,
`~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS) and add under `mcpServers`:

```json
{
  "mcpServers": {
    "jarvis-graph": {
      "command": "python",
      "args": ["-m", "jarvis_graph_mcp"],
      "env": {
        "JARVIS_GRAPH_LITE_PATH": "C:\\path\\to\\jarvis-graph-lite\\src"
      }
    }
  }
}
```

Restart Claude Desktop. The `jarvis-graph` server should appear in
the tool list.

### Claude Code

```bash
claude mcp add jarvis-graph python -m jarvis_graph_mcp
```

Or manually in your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "jarvis-graph": {
      "command": "python",
      "args": ["-m", "jarvis_graph_mcp"]
    }
  }
}
```

### Cursor / Windsurf / Cline

Add the same config block under their respective MCP settings. The
command and args are identical across clients because MCP is
transport-agnostic.

## Usage examples

Once connected, ask your LLM assistant questions like:

> "Use jarvis-graph to rank the top 5 refactor priorities in
> `C:\code\my-project`."

> "Find the top 10 coverage gaps in this repo and write test
> skeletons for the three most complex ones."

> "What's the call chain from `main` to `render_amv` in the
> lyrc-local repo?"

> "Run a full health report against `C:\code\current-project` and
> summarise the biggest risks."

The LLM picks the right tool, passes your repo path, and gets back
structured data it can reason about.

## Architecture

```
┌────────────────────────┐
│    MCP Client          │   Claude Desktop / Cursor /
│    (your editor)       │   Claude Code / Windsurf / ...
└──────────┬─────────────┘
           │ stdio (JSON-RPC)
┌──────────▼─────────────┐
│  jarvis-graph-mcp      │   this package
│  FastMCP server, 18    │
│  @mcp.tool decorators  │
└──────────┬─────────────┘
           │ subprocess + PYTHONPATH
┌──────────▼─────────────┐
│  jarvis-graph-lite     │   stdlib-only Python
│  CLI with --json flag  │   code index + query engine
└──────────┬─────────────┘
           │ read-only filesystem access
┌──────────▼─────────────┐
│  your source tree      │
└────────────────────────┘
```

All tools are **read-only**. This server cannot modify your code.
The worst it can do is read a file that shouldn't be indexed — and
even that is controlled by standard `.gitignore`-style exclusions in
jarvis-graph-lite.

## Development

```bash
# clone
git clone https://github.com/Zilli-on/jarvis-graph-mcp.git
cd jarvis-graph-mcp

# install in editable mode
pip install -e .

# verify the server starts and lists tools
python -c "
from jarvis_graph_mcp.server import mcp
import asyncio
tools = asyncio.run(mcp.list_tools())
print(f'{len(tools)} tools registered')
"
```

## Roadmap

- [x] V0.1: 18 tools, MCP stdio, subprocess backend, local-first
- [ ] V0.2: in-process jarvis-graph-lite integration (no subprocess
      fork per call, ~3x speedup for small queries)
- [ ] V0.3: `resources://` entries for health reports so clients can
      subscribe to "is my repo healthy?" as a live resource
- [ ] V0.4: TypeScript / JavaScript support (current: Python only)
- [ ] V0.5: Multi-repo mode — scan a whole workspace in one call

## License

MIT. See [LICENSE](LICENSE).

## Credits

Built on top of
[jarvis-graph-lite](https://github.com/Zilli-on/jarvis-graph-lite),
which does the actual static analysis. This package is the MCP
transport adapter.

If you find this useful, consider
[sponsoring](https://github.com/sponsors/Zilli-on).
