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

The checks below read the CLI's real argparse surface via
`jarvis_graph.cli._build_parser()` and compare it against what the MCP
layer actually sends. That happens in two layers, because the cheap one
has a blind spot:

  * `_record_backend_calls()` stubs `run_graph` and therefore sees only
    the *extra* arguments a tool hands over. No subprocess, no indexing,
    no lite checkout needed — but blind to everything `run_graph` adds
    on its own.
  * `_record_backend_argv()` stubs `subprocess.run` one level deeper, so
    the real argv is recorded: the `--json` that `run_graph` appends to
    every single call, the `index` subcommand that `ensure_indexed`
    fires ahead of most tools, and positional arguments. Each argv is
    then fed through the parser, which also rejects wrong positional
    arity — something no flag-name comparison can catch.

The second layer is not redundancy. Renaming `--json` inside `run_graph`
breaks every tool at runtime in exactly the way described above, and the
extras-only check stays green through all of it.

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


def _record_backend_argv() -> list[list[str]]:
	"""Call every registered tool with `subprocess.run` stubbed.

	Returns the full argv of each invocation, so assertions can see what
	`run_graph` builds — not merely what a tool handed to it. Needs a
	reachable lite checkout: `run_graph` resolves one before it assembles
	any arguments, and without it no argv is ever built.
	"""
	argvs: list[list[str]] = []

	class _CompletedStub:
		returncode = 0
		stdout = "{}"
		stderr = ""

	def fake_subprocess_run(args: list[str], **_: Any) -> _CompletedStub:
		argvs.append(list(args))
		return _CompletedStub()

	original_run = backend.subprocess.run
	backend.subprocess.run = fake_subprocess_run
	try:
		for tool in asyncio.run(srv.mcp.list_tools()):
			args: dict[str, Any] = {"repo_path": "/unused/by/this/test"}
			args.update(EXTRA_TOOL_ARGS.get(tool.name, {}))
			asyncio.run(srv.mcp.call_tool(tool.name, args))
	finally:
		backend.subprocess.run = original_run
	return argvs


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

	def test_real_argv_is_accepted_by_the_cli(self) -> None:
		rejected: list[str] = []
		for argv in _record_backend_argv():
			# `run_graph` builds [python, -m, jarvis_graph, command, ...].
			# Assert that shape rather than trusting the indices below:
			# a changed layout would otherwise parse the wrong slice and
			# quietly pass.
			self.assertEqual(
				argv[1:3],
				["-m", "jarvis_graph"],
				msg=f"run_graph argv layout changed: {argv[:4]}",
			)
			command, rest = argv[3], argv[4:]
			try:
				self.parser.parse_args([command, *rest])
			except SystemExit:
				rejected.append(" ".join([command, *rest]))
		self.assertFalse(
			rejected,
			msg=f"the CLI rejects argv the MCP layer builds: {sorted(rejected)}",
		)

	def test_argv_check_covers_the_implicit_index_call(self) -> None:
		# A guard for the guard. If `ensure_indexed` stops firing — or gets
		# stubbed away as it is in `_record_backend_calls` — the check above
		# would silently lose its only coverage of the `index` subcommand
		# and still report green. This makes that loss loud.
		commands = {argv[3] for argv in _record_backend_argv()}
		self.assertIn(
			"index",
			commands,
			msg="ensure_indexed no longer reaches the backend",
		)


if __name__ == "__main__":
	unittest.main()
