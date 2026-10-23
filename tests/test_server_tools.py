"""Error-path and payload-wrapping tests for the MCP tool surface.

`test_smoke.py` only proves registration, and `test_cli_contract.py`
only proves the flag *names* a tool sends. Neither pins what a tool
returns when the backend fails, which wrapper key each payload is
filed under, or the fact that `GraphBackendError` is converted into a
clean ``{"error": ..., "tool_version": ...}`` dict while anything
unexpected still propagates. This file pins, for every one of the 18
registered tools:

  * the subprocess wiring (`run_graph` called once, with the right
    subcommand, repo and extra arguments, in the right order),
  * which tools index first (`ensure_indexed` for all but
    `detect_changes`),
  * the wrapper key each list payload is filed under and which tools
    pass a dict payload through unchanged,
  * the exact error dict returned when the backend (or the indexing
    step) raises `GraphBackendError`,
  * that unexpected exceptions are NOT swallowed into error dicts.

The CLI is never spawned: `server.run_graph` and `server.ensure_indexed`
are the module-level names the tools resolve, so patching them with
recording fakes isolates the layer completely. Assertions are exact
(dict equality with expected keys/wording) so that a behavioural
mutation — a renamed wrapper key, a dropped `tool_version`, a widened
`except` clause — makes at least one test here fail.
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import contextmanager
from typing import Any
from unittest import mock

from mcp.server.fastmcp.exceptions import ToolError

from jarvis_graph_mcp import __version__
from jarvis_graph_mcp import backend
from jarvis_graph_mcp import server as srv

REPO = "C:/jg-test/demo-repo"
LIST_PAYLOAD: list[Any] = [{"symbol": "foo", "score": 2}]
DICT_PAYLOAD: dict[str, Any] = {"files": 3, "symbols": 12}
ERR_MSG = "backend down"


# Per-tool expectations, spelled out explicitly (not generated) so a
# tool's wiring can only drift if its row drifts.
#   args      — arguments beyond repo_path the tool accepts
#   extras    — the extra arguments expected in the run_graph call
#   list_key  — wrapper key for a list payload
#   dict_key  — wrapper key for a dict payload, or None = as-is
#   ensure    — whether the tool indexes first
TOOL_SPECS: dict[str, dict[str, Any]] = {
	"refactor_priority": {
		"args": {"limit": 3, "min_priority": 12.5},
		"extras": ("--limit", "3", "--min-priority", "12.5"),
		"list_key": "candidates",
		"dict_key": "candidates",
		"ensure": True,
	},
	"find_coverage_gaps": {
		"args": {"limit": 4, "min_complexity": 2},
		"extras": ("--limit", "4", "--min-complexity", "2"),
		"list_key": "gaps",
		"dict_key": "gaps",
		"ensure": True,
	},
	"generate_test_skeleton": {
		"args": {"symbol": "pkg.mod.Foo"},
		"extras": ("pkg.mod.Foo",),
		"list_key": "skeleton",
		"dict_key": "skeleton",
		"ensure": True,
	},
	"health_report": {
		"args": {},
		"extras": (),
		"list_key": "report",
		"dict_key": None,
		"ensure": True,
	},
	"detect_changes": {
		"args": {},
		"extras": (),
		"list_key": "changes",
		"dict_key": None,
		"ensure": False,
	},
	"summary": {
		"args": {},
		"extras": (),
		"list_key": "summary",
		"dict_key": None,
		"ensure": True,
	},
	"query": {
		"args": {"term": "auth", "limit": 7},
		"extras": ("auth", "--limit", "7"),
		"list_key": "matches",
		"dict_key": "matches",
		"ensure": True,
	},
	"context": {
		"args": {"symbol": "auth.login"},
		"extras": ("auth.login",),
		"list_key": "context",
		"dict_key": None,
		"ensure": True,
	},
	"impact": {
		"args": {"symbol": "auth.User"},
		"extras": ("auth.User",),
		"list_key": "impact",
		"dict_key": None,
		"ensure": True,
	},
	"find_path": {
		"args": {"source": "a.f", "target": "b.g"},
		"extras": ("a.f", "b.g"),
		"list_key": "path",
		"dict_key": None,
		"ensure": True,
	},
	"find_dead_code": {
		"args": {"limit": 5},
		"extras": ("--limit", "5"),
		"list_key": "dead_symbols",
		"dict_key": "dead_symbols",
		"ensure": True,
	},
	"find_unused_imports": {
		"args": {"limit": 6},
		"extras": ("--limit", "6"),
		"list_key": "unused",
		"dict_key": "unused",
		"ensure": True,
	},
	"find_circular_deps": {
		"args": {},
		"extras": (),
		"list_key": "cycles",
		"dict_key": "cycles",
		"ensure": True,
	},
	"find_complexity": {
		"args": {"threshold": 9, "limit": 8},
		"extras": ("--threshold", "9", "--limit", "8"),
		"list_key": "hotspots",
		"dict_key": "hotspots",
		"ensure": True,
	},
	"find_long_functions": {
		"args": {"min_lines": 60, "limit": 9},
		"extras": ("--threshold", "60", "--limit", "9"),
		"list_key": "long_functions",
		"dict_key": "long_functions",
		"ensure": True,
	},
	"find_god_files": {
		"args": {"limit": 3},
		"extras": ("--limit", "3"),
		"list_key": "god_files",
		"dict_key": "god_files",
		"ensure": True,
	},
	"find_high_fan_out": {
		"args": {"limit": 2},
		"extras": ("--limit", "2"),
		"list_key": "high_fan_out",
		"dict_key": "high_fan_out",
		"ensure": True,
	},
	"find_todo_comments": {
		"args": {"limit": 4},
		"extras": ("--limit", "4"),
		"list_key": "todos",
		"dict_key": "todos",
		"ensure": True,
	},
}


@contextmanager
def _stubbed_tools(run_effect: object = None, ensure_effect: object = None):
	"""Patch `srv.run_graph` and `srv.ensure_indexed` with recording fakes.

	An effect that is an exception instance is raised; anything else is
	returned. Yields `(run_calls, ensure_calls)` for verification.
	"""
	run_calls: list[tuple[str, str, tuple[str, ...]]] = []
	ensure_calls: list[str] = []

	def fake_run(command: str, repo: str, *extra: str, **kwargs: Any) -> object:
		run_calls.append((command, repo, extra))
		if isinstance(run_effect, BaseException):
			raise run_effect
		return run_effect

	def fake_ensure(repo: str) -> None:
		ensure_calls.append(repo)
		if isinstance(ensure_effect, BaseException):
			raise ensure_effect

	with (
		mock.patch.object(srv, "run_graph", fake_run),
		mock.patch.object(srv, "ensure_indexed", fake_ensure),
	):
		yield run_calls, ensure_calls


def _call_tool(name: str) -> dict[str, Any]:
	"""Invoke a tool through FastMCP and return its structured payload."""
	spec = TOOL_SPECS[name]
	tool_args: dict[str, Any] = {"repo_path": REPO}
	tool_args.update(spec["args"])
	result = asyncio.run(srv.mcp.call_tool(name, tool_args))
	if isinstance(result, tuple):
		structured = result[1]
	elif isinstance(result, list):
		raise AssertionError(f"no structured content for {name}: {result!r}")
	else:
		structured = result
	return structured


class ToolBackendWiringTests(unittest.TestCase):
	"""What each tool hands to the backend, in which order."""

	def test_run_graph_called_once_with_expected_command_and_extras(self) -> None:
		# The payload value is irrelevant here; only the wiring is pinned.
		with _stubbed_tools(run_effect=LIST_PAYLOAD) as (run_calls, _):
			for name in TOOL_SPECS:
				_call_tool(name)
		self.assertEqual(
			run_calls,
			[(name, REPO, spec["extras"]) for name, spec in TOOL_SPECS.items()],
		)

	def test_ensure_indexed_runs_before_querying_every_subscript_tool(self) -> None:
		with _stubbed_tools(run_effect=DICT_PAYLOAD) as (_, ensure_calls):
			for name in TOOL_SPECS:
				_call_tool(name)
		expected = [
			REPO for name, spec in TOOL_SPECS.items() if spec["ensure"]
		]
		self.assertEqual(ensure_calls, expected)
		self.assertNotIn(
			"detect_changes",
			[n for n, s in TOOL_SPECS.items() if s["ensure"]],
		)


class PayloadWrappingTests(unittest.TestCase):
	"""The wrapper key each payload kind is filed under."""

	def test_list_payloads_are_wrapped_under_the_documented_key(self) -> None:
		with _stubbed_tools(run_effect=LIST_PAYLOAD):
			for name, spec in TOOL_SPECS.items():
				structured = _call_tool(name)
				self.assertEqual(
					structured,
					{spec["list_key"]: LIST_PAYLOAD},
					msg=f"{name} files list payloads under the wrong key",
				)

	def test_dict_payloads_go_through_unchanged_or_via_their_key(self) -> None:
		with _stubbed_tools(run_effect=DICT_PAYLOAD):
			for name, spec in TOOL_SPECS.items():
				structured = _call_tool(name)
				if spec["dict_key"] is None:
					expected = DICT_PAYLOAD
				else:
					expected = {spec["dict_key"]: DICT_PAYLOAD}
				self.assertEqual(
					structured,
					expected,
					msg=f"{name} files dict payloads under the wrong key",
				)


class ToolErrorPathTests(unittest.TestCase):
	"""What a tool returns when the backend cannot answer."""

	_ERROR_RESULT = {"error": ERR_MSG, "tool_version": __version__}

	def test_backend_failure_returns_exact_error_dict_for_every_tool(self) -> None:
		with _stubbed_tools(
			run_effect=backend.GraphBackendError(ERR_MSG),
			ensure_effect=backend.GraphBackendError(ERR_MSG),
		):
			for name in TOOL_SPECS:
				structured = _call_tool(name)
				self.assertEqual(
					structured,
					self._ERROR_RESULT,
					msg=f"{name} mishandles a backend failure",
				)

	def test_indexing_failure_short_circuits_before_the_query(self) -> None:
		# `ensure_indexed` runs ahead of the real command: its failure
		# must surface as the error dict, and the query must not run.
		ensure_msg = "index failed hard"
		effect = backend.GraphBackendError(ensure_msg)
		with _stubbed_tools(
			run_effect=LIST_PAYLOAD,
			ensure_effect=effect,
		) as (run_calls, _):
			structured = _call_tool("refactor_priority")
		self.assertEqual(
			structured,
			{"error": ensure_msg, "tool_version": __version__},
		)
		self.assertEqual(run_calls, [])

	def test_detect_changes_reports_its_own_backend_failure(self) -> None:
		# detect_changes does not index, so its error must come from the
		# query path — not from the (never-called) indexing stub.
		run_effect = backend.GraphBackendError(ERR_MSG)
		ensure_effect = RuntimeError("ensure_indexed must not be called")
		with _stubbed_tools(
			run_effect=run_effect,
			ensure_effect=ensure_effect,
		):
			for name, spec in TOOL_SPECS.items():
				if spec["ensure"]:
					continue
				structured = _call_tool(name)
				self.assertEqual(
					structured,
					self._ERROR_RESULT,
					msg=f"{name} mishandles a backend failure",
				)

	def test_unexpected_errors_are_not_swallowed_into_error_dicts(self) -> None:
		# Only GraphBackendError maps to {"error": ...}. Any other
		# exception must propagate (FastMCP wraps it as ToolError) so
		# programming errors stay loud instead of masquerading as
		# legitimate backend outages.
		for name in ("refactor_priority", "detect_changes"):
			with _stubbed_tools(run_effect=RuntimeError("not a backend failure")):
				with self.assertRaises(ToolError):
					_call_tool(name)


class EntryPointTests(unittest.TestCase):
	def test_main_starts_the_stdio_transport(self) -> None:
		run_recorder = mock.MagicMock()
		with mock.patch.object(srv.mcp, "run", run_recorder):
			srv.main()
		run_recorder.assert_called_once_with(transport="stdio")


if __name__ == "__main__":
	unittest.main()
