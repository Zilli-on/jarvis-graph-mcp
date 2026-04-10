"""FastMCP server exposing the jarvis-graph-lite command surface.

Each `@mcp.tool()` below is a thin wrapper around `backend.run_graph`.
The tool signatures match what the underlying lite CLI expects so the
LLM caller can reason about inputs naturally:

    refactor_priority(repo_path="/path/to/repo", limit=10)
    find_coverage_gaps(repo_path="/path/to/repo", min_complexity=5)
    generate_test_skeleton(repo_path="/path/to/repo", symbol="Foo.bar")
    ...

All tools are read-only. None of them modify the user's source tree.

Transport: stdio (the MCP default). Clients register this as a
command server by adding an entry to their mcp.json or equivalent:

    {
      "jarvis-graph": {
        "command": "python",
        "args": ["-m", "jarvis_graph_mcp"]
      }
    }
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .backend import GraphBackendError, ensure_indexed, run_graph

mcp: FastMCP = FastMCP(
	name="jarvis-graph",
	instructions=(
		"Local-first code intelligence for Python repos. Use these tools "
		"to find refactor priorities, untested hotspots, dead code, import "
		"cycles, complexity issues, and actionable TODO comments — all "
		"without uploading source to any cloud service. Every tool takes "
		"a `repo_path` (absolute path to a Python repository root) and "
		"returns a structured result you can reason about."
	),
)


# ---------- helpers -----------------------------------------------------


def _as_error(exc: Exception) -> dict[str, Any]:
	"""Convert a backend error into an LLM-friendly dict.

	FastMCP returns whatever the tool function returns, so a plain
	dict with `error` flags the failure clearly without raising an
	exception that would bubble up to the transport layer.
	"""
	return {"error": str(exc), "tool_version": __version__}


# ---------- refactor priorities + coverage + tests ---------------------


@mcp.tool(
	name="refactor_priority",
	description=(
		"Rank the top N untested complexity hotspots in a Python repo. "
		"Combines cyclomatic complexity, line count, caller count, and "
		"test coverage into one composite score. Use this to answer "
		"'what should I refactor first?'"
	),
)
def refactor_priority(
	repo_path: str,
	limit: int = 10,
	min_priority: float = 50.0,
) -> dict[str, Any]:
	"""Returns a ranked list of refactor candidates."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"refactor_priority",
			repo_path,
			"--limit",
			str(limit),
			"--min-priority",
			str(min_priority),
		)
		return {"candidates": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_coverage_gaps",
	description=(
		"List public symbols in a repo that no test entry point can reach "
		"via the call graph. Use this to find where to add tests next."
	),
)
def find_coverage_gaps(
	repo_path: str,
	limit: int = 50,
	min_complexity: int = 1,
) -> dict[str, Any]:
	"""Returns untested reachable symbols ranked by risk."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_coverage_gaps",
			repo_path,
			"--limit",
			str(limit),
			"--min-complexity",
			str(min_complexity),
		)
		return {"gaps": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="generate_test_skeleton",
	description=(
		"Emit a unittest.TestCase skeleton for a given symbol. Pairs "
		"with `find_coverage_gaps` to close the 'what's untested → "
		"write a stub' loop: find the gap, then call this tool with "
		"the symbol name to get a starter file."
	),
)
def generate_test_skeleton(
	repo_path: str,
	symbol: str,
) -> dict[str, Any]:
	"""Returns the generated Python source for a test skeleton."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"generate_test_skeleton",
			repo_path,
			symbol,
		)
		return {"skeleton": data}
	except GraphBackendError as exc:
		return _as_error(exc)


# ---------- health + drift ----------------------------------------------


@mcp.tool(
	name="health_report",
	description=(
		"Full-repo health scan combining every signal: complexity, "
		"coverage, dead code, cycles, unused imports, god files, TODO "
		"density, and fan-out coupling. Use at the start of a session "
		"to get a one-shot overview of the codebase state."
	),
)
def health_report(repo_path: str) -> dict[str, Any]:
	"""Returns the structured health report."""
	try:
		ensure_indexed(repo_path)
		data = run_graph("health_report", repo_path)
		return data if isinstance(data, dict) else {"report": data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="detect_changes",
	description=(
		"Diff the current filesystem against the last cached index. "
		"Shows which files were added, modified, or removed since the "
		"last index run. Use this to know what changed between sessions."
	),
)
def detect_changes(repo_path: str) -> dict[str, Any]:
	"""Returns an added/modified/removed file list."""
	try:
		data = run_graph("detect_changes", repo_path)
		return data if isinstance(data, dict) else {"changes": data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="summary",
	description=(
		"Deterministic per-repo summary: file count, symbol count, "
		"import count, call count, indexed size. Stable across runs "
		"on the same commit."
	),
)
def summary(repo_path: str) -> dict[str, Any]:
	"""Returns the repo summary structure."""
	try:
		ensure_indexed(repo_path)
		data = run_graph("summary", repo_path)
		return data if isinstance(data, dict) else {"summary": data}
	except GraphBackendError as exc:
		return _as_error(exc)


# ---------- symbol-level queries ----------------------------------------


@mcp.tool(
	name="query",
	description=(
		"Locate where a concept lives in the repo. Pass a keyword or "
		"partial symbol name and get back the files and symbols that "
		"match. Use this as the entry point to 'where is X implemented?'"
	),
)
def query(repo_path: str, term: str, limit: int = 20) -> dict[str, Any]:
	"""Returns matching symbols/files."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"query",
			repo_path,
			term,
			"--limit",
			str(limit),
		)
		return {"matches": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="context",
	description=(
		"Explain a symbol's role in the codebase: what it calls, what "
		"calls it, what file it lives in, how complex it is. Use this "
		"after `query` to drill into a specific symbol."
	),
)
def context(repo_path: str, symbol: str) -> dict[str, Any]:
	"""Returns symbol context (callers, callees, complexity)."""
	try:
		ensure_indexed(repo_path)
		data = run_graph("context", repo_path, symbol)
		return data if isinstance(data, dict) else {"context": data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="impact",
	description=(
		"Estimate the blast radius of modifying a symbol. Returns the "
		"transitive set of callers that would be affected by a change. "
		"Use this before refactoring to know what you're touching."
	),
)
def impact(repo_path: str, symbol: str, depth: int = 3) -> dict[str, Any]:
	"""Returns the transitive caller set."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"impact",
			repo_path,
			symbol,
			"--depth",
			str(depth),
		)
		return data if isinstance(data, dict) else {"impact": data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_path",
	description=(
		"Find a shortest resolved call chain between two symbols. "
		"Answers 'how does foo eventually end up calling bar?' in a "
		"single hop."
	),
)
def find_path(
	repo_path: str,
	source: str,
	target: str,
) -> dict[str, Any]:
	"""Returns the call chain as an ordered list of symbols."""
	try:
		ensure_indexed(repo_path)
		data = run_graph("find_path", repo_path, source, target)
		return data if isinstance(data, dict) else {"path": data}
	except GraphBackendError as exc:
		return _as_error(exc)


# ---------- debt detection ---------------------------------------------


@mcp.tool(
	name="find_dead_code",
	description=(
		"List functions, classes, and methods that have no callers "
		"anywhere in the repo. Has built-in false-positive filters for "
		"test classes, dispatch dicts, and module-level convention names."
	),
)
def find_dead_code(
	repo_path: str,
	limit: int = 50,
) -> dict[str, Any]:
	"""Returns likely-dead symbols."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_dead_code",
			repo_path,
			"--limit",
			str(limit),
		)
		return {"dead_symbols": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_unused_imports",
	description=(
		"List unused import statements in a Python repo. Honours "
		"`# noqa: F401` annotations to skip intentional re-exports."
	),
)
def find_unused_imports(
	repo_path: str,
	limit: int = 100,
) -> dict[str, Any]:
	"""Returns unused imports grouped by file."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_unused_imports",
			repo_path,
			"--limit",
			str(limit),
		)
		return {"unused": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_circular_deps",
	description=(
		"Detect import cycles between modules. A cycle is almost always "
		"a refactoring smell; use this to catch them before they calcify."
	),
)
def find_circular_deps(repo_path: str) -> dict[str, Any]:
	"""Returns detected import cycles."""
	try:
		ensure_indexed(repo_path)
		data = run_graph("find_circular_deps", repo_path)
		return {"cycles": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_complexity",
	description=(
		"List functions and methods with cyclomatic complexity above a "
		"threshold. Higher complexity = harder to test, more likely to "
		"hide bugs."
	),
)
def find_complexity(
	repo_path: str,
	threshold: int = 10,
	limit: int = 50,
) -> dict[str, Any]:
	"""Returns complex symbols ranked by score."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_complexity",
			repo_path,
			"--threshold",
			str(threshold),
			"--limit",
			str(limit),
		)
		return {"hotspots": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_long_functions",
	description=(
		"List functions and methods over a line-count threshold. Long "
		"functions are a proxy for scope creep and often correlate with "
		"high complexity."
	),
)
def find_long_functions(
	repo_path: str,
	min_lines: int = 50,
	limit: int = 50,
) -> dict[str, Any]:
	"""Returns long functions ranked by length."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_long_functions",
			repo_path,
			"--min-lines",
			str(min_lines),
			"--limit",
			str(limit),
		)
		return {"long_functions": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_god_files",
	description=(
		"Rank files by symbols × LOC × fan-in. God files concentrate "
		"too much responsibility and become refactoring bottlenecks."
	),
)
def find_god_files(
	repo_path: str,
	limit: int = 20,
) -> dict[str, Any]:
	"""Returns ranked god file candidates."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_god_files",
			repo_path,
			"--limit",
			str(limit),
		)
		return {"god_files": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_high_fan_out",
	description=(
		"List files that import many other in-repo files. High fan-out "
		"indicates coupling risk — changing a high-fan-out file ripples "
		"through more of the codebase."
	),
)
def find_high_fan_out(
	repo_path: str,
	limit: int = 20,
) -> dict[str, Any]:
	"""Returns high-fan-out files ranked by import count."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_high_fan_out",
			repo_path,
			"--limit",
			str(limit),
		)
		return {"high_fan_out": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


@mcp.tool(
	name="find_todo_comments",
	description=(
		"Rank TODO/FIXME/HACK/BUG/XXX comments by composite risk (tag "
		"severity + complexity + line count of the enclosing symbol). "
		"Use this to find the author-annotated debt that actually "
		"matters instead of every stray 'TODO' in the codebase."
	),
)
def find_todo_comments(
	repo_path: str,
	limit: int = 50,
) -> dict[str, Any]:
	"""Returns TODO comments ranked by risk."""
	try:
		ensure_indexed(repo_path)
		data = run_graph(
			"find_todo_comments",
			repo_path,
			"--limit",
			str(limit),
		)
		return {"todos": data if isinstance(data, list) else data}
	except GraphBackendError as exc:
		return _as_error(exc)


# ---------- entry point -------------------------------------------------


def main() -> None:
	"""Start the FastMCP server over stdio."""
	mcp.run(transport="stdio")


if __name__ == "__main__":
	main()
