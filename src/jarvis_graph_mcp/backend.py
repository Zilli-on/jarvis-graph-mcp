"""Thin subprocess wrapper around the bundled jarvis-graph-lite CLI.

Every MCP tool in `server.py` routes through here. Keeping the
subprocess plumbing in one file makes it:
  1. trivial to swap for an in-process call later,
  2. easy to mock for tests (patch `run_graph`),
  3. the single place where the Python interpreter + module path are
     resolved — no scattered path logic across tool definitions.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


class GraphBackendError(RuntimeError):
	"""Raised when jarvis-graph-lite cannot be located or crashes."""


def _find_graph_lite_path() -> Path | None:
	"""Locate the jarvis-graph-lite source directory.

	Resolution order:
	  1. `JARVIS_GRAPH_LITE_PATH` environment variable (absolute path
	     to the `src` directory of the lite package).
	  2. A sibling clone at `../jarvis-graph-lite/src` relative to
	     this file (the layout used in the authoring workspace).
	  3. A well-known install location on Windows: `C:\\JARVIS\\tools
	     \\jarvis-graph-lite\\src`.

	Returns the first path that exists, or None if nothing was found.
	"""
	env_hint = os.environ.get("JARVIS_GRAPH_LITE_PATH")
	if env_hint:
		candidate = Path(env_hint)
		if candidate.exists():
			return candidate

	here = Path(__file__).resolve()
	sibling = here.parents[3] / "jarvis-graph-lite" / "src"
	if sibling.exists():
		return sibling

	windows_default = Path("C:/JARVIS/tools/jarvis-graph-lite/src")
	if windows_default.exists():
		return windows_default

	return None


def _python_executable() -> str:
	"""Return the Python interpreter to spawn the lite CLI with.

	Honours `JARVIS_GRAPH_PYTHON` for bespoke setups (e.g. a
	project-specific venv), otherwise falls back to the interpreter
	that's running this MCP server — which is what most users will
	want because it guarantees the same stdlib version.
	"""
	env_hint = os.environ.get("JARVIS_GRAPH_PYTHON")
	if env_hint and shutil.which(env_hint):
		return env_hint
	return sys.executable


def run_graph(
	command: str,
	repo: str,
	*extra_args: str,
	timeout_s: int = 120,
) -> dict | list:
	"""Invoke `jarvis-graph <command> <repo> --json [extras]`.

	Returns the parsed JSON payload (dict or list depending on the
	command). Raises `GraphBackendError` on any failure so the MCP
	server can turn it into a clean error response for the LLM.
	"""
	graph_path = _find_graph_lite_path()
	if graph_path is None:
		raise GraphBackendError(
			"jarvis-graph-lite not found. Set JARVIS_GRAPH_LITE_PATH or "
			"install the package at C:/JARVIS/tools/jarvis-graph-lite."
		)

	python = _python_executable()
	env = {**os.environ, "PYTHONPATH": str(graph_path)}
	args = [python, "-m", "jarvis_graph", command, repo, "--json", *extra_args]

	try:
		proc = subprocess.run(
			args,
			capture_output=True,
			text=True,
			timeout=timeout_s,
			env=env,
		)
	except subprocess.TimeoutExpired as exc:
		raise GraphBackendError(
			f"jarvis-graph {command} timed out after {timeout_s}s on {repo}"
		) from exc
	except FileNotFoundError as exc:
		raise GraphBackendError(
			f"Python interpreter not found: {python}"
		) from exc

	if proc.returncode != 0:
		stderr = (proc.stderr or "").strip()
		raise GraphBackendError(
			f"jarvis-graph {command} failed (rc={proc.returncode}): {stderr[:500]}"
		)

	payload = (proc.stdout or "").strip()
	if not payload:
		return []

	try:
		return json.loads(payload)
	except json.JSONDecodeError as exc:
		raise GraphBackendError(
			f"jarvis-graph {command} returned non-JSON output: {payload[:300]}"
		) from exc


def ensure_indexed(repo: str) -> None:
	"""Run `jarvis-graph index <repo>` once so downstream queries hit
	a fresh index. No-op if the index is already current — the index
	command is itself idempotent and fast for unchanged files.
	"""
	run_graph("index", repo)


__all__ = ["GraphBackendError", "run_graph", "ensure_indexed"]
