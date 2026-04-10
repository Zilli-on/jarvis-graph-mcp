"""Minimal smoke tests for jarvis-graph-mcp.

These tests verify that:
  1. The FastMCP server module imports cleanly.
  2. Every @mcp.tool decorator registers successfully.
  3. The expected tool count matches the advertised surface (18).

No subprocess calls — those are integration territory and require a
real jarvis-graph-lite checkout. The in-process smoke test here runs
in milliseconds and catches the most common breakage: import errors
after a refactor, missing decorators, or duplicate tool names.
"""

from __future__ import annotations

import asyncio
import unittest


EXPECTED_TOOL_NAMES = {
	"refactor_priority",
	"find_coverage_gaps",
	"generate_test_skeleton",
	"health_report",
	"detect_changes",
	"summary",
	"query",
	"context",
	"impact",
	"find_path",
	"find_dead_code",
	"find_unused_imports",
	"find_circular_deps",
	"find_complexity",
	"find_long_functions",
	"find_god_files",
	"find_high_fan_out",
	"find_todo_comments",
}


class ServerImportTests(unittest.TestCase):
	def test_server_module_imports(self) -> None:
		from jarvis_graph_mcp.server import mcp  # noqa: F401
		self.assertIsNotNone(mcp)

	def test_main_entry_point_exists(self) -> None:
		from jarvis_graph_mcp.server import main
		self.assertTrue(callable(main))


class ToolSurfaceTests(unittest.TestCase):
	def _get_tools(self) -> list:
		from jarvis_graph_mcp.server import mcp
		return asyncio.run(mcp.list_tools())

	def test_all_expected_tools_registered(self) -> None:
		tools = self._get_tools()
		names = {t.name for t in tools}
		missing = EXPECTED_TOOL_NAMES - names
		extra = names - EXPECTED_TOOL_NAMES
		self.assertFalse(
			missing,
			msg=f"Missing tools: {sorted(missing)}",
		)
		self.assertFalse(
			extra,
			msg=f"Unexpected extra tools: {sorted(extra)}",
		)

	def test_tool_count_is_eighteen(self) -> None:
		tools = self._get_tools()
		self.assertEqual(len(tools), 18)

	def test_every_tool_has_a_description(self) -> None:
		tools = self._get_tools()
		for t in tools:
			self.assertTrue(
				t.description and len(t.description.strip()) > 20,
				msg=f"Tool {t.name!r} has no usable description",
			)


class BackendErrorHandlingTests(unittest.TestCase):
	def test_missing_repo_path_returns_error_dict(self) -> None:
		# Call a tool with a repo path that doesn't exist. The backend
		# should raise GraphBackendError and the tool should convert it
		# to a clean {"error": ...} dict rather than let the exception
		# bubble up.
		from jarvis_graph_mcp.server import mcp

		async def call() -> object:
			return await mcp.call_tool(
				"refactor_priority",
				{"repo_path": "/this/path/does/not/exist/ever"},
			)

		result = asyncio.run(call())
		# FastMCP returns (content_blocks, structured_data)
		if isinstance(result, tuple):
			_, structured = result
		else:
			structured = result
		# Either an error dict or a candidates dict wrapping an error
		self.assertIsInstance(structured, dict)


if __name__ == "__main__":
	unittest.main()
