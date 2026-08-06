"""Contract test: every CLI flag the MCP layer passes must actually exist.

`test_smoke.py` checks the tool *surface* — names, count, descriptions.
That is necessary but it cannot catch the failure mode this file targets:
a tool that is registered, described, and reachable, yet passes a flag the
`jarvis-graph` CLI has never accepted. argparse answers rc=2, `run_graph`
turns it into a `GraphBackendError`, and the tool returns a tidy
`{"error": ...}` dict — so nothing crashes, the suite stays green, and the
tool is 100 % broken for every input.

Two tools shipped exactly like that until 2026-08-06:

  * `impact` passed `--depth`, which the CLI does not define at all
    (`impact [--json] repo target`),
  * `find_long_functions` passed `--min-lines`, which the CLI spells
    `--threshold`.

The check below reads the CLI's real argparse surface via
`jarvis_graph.cli._build_parser()`, records what every registered MCP tool
would pass by stubbing `run_graph`, and compares the two. No subprocess and
no indexing — it is a pure wiring check.

It is skipped when no jarvis-graph-lite checkout is reachable (the lite
package is resolved at runtime, not a pip dependency), so a bare clone of
this repo still runs a green suite.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import unittest
from typing import Any

from jarvis_graph_mcp import backend
from jarvis_graph_mcp import server as srv


# Tools that need more than `repo_path`. `run_graph` is stubbed out, so
# these values are never resolved against a real repo — they only have to
# satisfy the tool signatures.
EXTRA_TOOL_ARGS: dict[str, dict[str, Any]] = {
	"generate_test_skeleton": {"symbol": "some_symbol"},
	"query": {"term": "some_term"},
	"context": {"symbol": "some_symbol"},
	"impact": {"symbol": "some_symbol"},
	"find_path": {"source": "some_source", "target": "some_target"},
}


def _lite_parser() -> argparse.ArgumentParser | None:
	"""Build the jarvis-graph-lite argparse parser, or None if absent."""
	lite_src = backend._find_graph_lite_path()
	if lite_src is None:
		return None
	if str(lite_src) not in sys.path:
		sys.path.insert(0, str(lite_src))
	try:
		from jarvis_graph.cli import _build_parser
	except ImportError:
		return None
	return _build_parser()


def _accepted_options(parser: argparse.ArgumentParser) -> dict[str, set[str]]:
	"""Map each subcommand name to the option strings it accepts."""
	accepted: dict[str, set[str]] = {}
	for action in parser._actions:
		if not isinstance(action, argparse._SubParsersAction):
			continue
		for name, subparser in action.choices.items():
			options: set[str] = set()
			for sub_action in subparser._actions:
				options.update(sub_action.option_strings)
			accepted[name] = options
	return accepted


def _record_backend_calls() -> list[tuple[str, tuple[str, ...]]]:
	"""Call every registered tool with `run_graph` stubbed, return the calls."""
	calls: list[tuple[str, tuple[str, ...]]] = []

	def fake_run_graph(command: str, repo: str, *extra: str, **_: Any) -> dict:
		calls.append((command, extra))
		return {}

	original_run_graph = srv.run_graph
	original_ensure_indexed = srv.ensure_indexed
	srv.run_graph = fake_run_graph
	srv.ensure_indexed = lambda repo: None
	try:
		for tool in asyncio.run(srv.mcp.list_tools()):
			args: dict[str, Any] = {"repo_path": "/unused/by/this/test"}
			args.update(EXTRA_TOOL_ARGS.get(tool.name, {}))
			asyncio.run(srv.mcp.call_tool(tool.name, args))
	finally:
		srv.run_graph = original_run_graph
		srv.ensure_indexed = original_ensure_indexed
	return calls


class BackendCallShapeTests(unittest.TestCase):
	"""Checks that need no jarvis-graph-lite checkout."""

	def test_every_tool_reaches_the_backend(self) -> None:
		calls = _record_backend_calls()
		tool_count = len(asyncio.run(srv.mcp.list_tools()))
		self.assertGreaterEqual(
			len(calls),
			tool_count,
			msg="a registered tool never called run_graph",
		)

	def test_all_extra_args_are_strings(self) -> None:
		# subprocess.run rejects non-str argv entries; an int limit that
		# slipped through un-str()ed would only surface at call time.
		for command, extra in _record_backend_calls():
			for arg in extra:
				self.assertIsInstance(
					arg,
					str,
					msg=f"{command} passes non-str argument {arg!r}",
				)


class CliFlagContractTests(unittest.TestCase):
	"""The real check: flags passed must exist in the CLI."""

	def setUp(self) -> None:
		self.parser = _lite_parser()
		if self.parser is None:
			self.skipTest("no jarvis-graph-lite checkout reachable")
		self.accepted = _accepted_options(self.parser)

	def test_every_command_exists_in_the_cli(self) -> None:
		for command, _ in _record_backend_calls():
			self.assertIn(
				command,
				self.accepted,
				msg=f"MCP layer calls unknown subcommand {command!r}",
			)

	def test_every_flag_is_accepted_by_its_command(self) -> None:
		unknown: list[str] = []
		for command, extra in _record_backend_calls():
			options = self.accepted.get(command)
			if options is None:
				continue  # covered by the test above
			for arg in extra:
				if arg.startswith("--") and arg not in options:
					unknown.append(f"{command} {arg}")
		self.assertFalse(
			unknown,
			msg=(f"MCP layer passes flags the CLI does not define: {sorted(unknown)}"),
		)


if __name__ == "__main__":
	unittest.main()
