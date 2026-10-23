"""Behaviour tests for the subprocess backend (jarvis_graph_mcp.backend).

`test_smoke.py` and `test_cli_contract.py` treat `backend.py` as a black
box: they never exercise its own branches. On a machine that has a real
jarvis-graph-lite checkout, the happy path happens to run against the
filesystem — but every error branch (missing checkout, dead interpreter,
non-zero exit, timeout, non-JSON output) was uncovered, and so was the
path-resolution order in `_find_graph_lite_path` and the interpreter
preference in `_python_executable`.

These tests pin all of that without touching the real machine:

  * Filesystem lookups are decided by patching `pathlib.Path.exists`
    with a stub that only recognises the fake paths under test.
  * Environment is controlled with `unittest.mock.patch.dict`.
  * `subprocess.run` never launches anything; a recorder fake returns a
    chosen `CompletedProcess` (or raises a chosen exception) and keeps
    the argv/kwargs of every call for exact-shape assertions.

A deliberate mutation of any of the piped values (env var order, the
`--json` flag, `PYTHONPATH`, timeout, interpreter choice, error message
wording, stderr truncation length) makes at least one assertion here
fail, so the tests survive mutation testing rather than merely
asserting "no exception".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from jarvis_graph_mcp import backend

# Fake paths that exist nowhere on a real filesystem.
LITE_SRC = "Q:/jg-test/lite/src"
REPO = "C:/jg-test/demo-repo"
NOT_FOUND_MSG = (
	"jarvis-graph-lite not found. Set JARVIS_GRAPH_LITE_PATH or "
	"install the package at C:/JARVIS/tools/jarvis-graph-lite."
)


def _exists_only_for(*allowed: object):
	"""Return a `Path.exists` stub that is True exactly for `allowed` paths."""

	real = {str(Path(a)) for a in allowed}

	def exists(self: Path) -> bool:
		return str(self) in real

	return exists


def _completed(*, returncode: int = 0, stdout: str = "{}", stderr: str = ""):
	proc = subprocess.CompletedProcess(args=[], returncode=returncode)
	proc.stdout = stdout
	proc.stderr = stderr
	return proc


def _sibling_of_mcp_package() -> Path:
	"""The sibling clone path rule from `_find_graph_lite_path` rule #2."""
	return Path(backend.__file__).resolve().parents[3] / "jarvis-graph-lite" / "src"


class _patched_backend:
	"""Patch the lite lookup and `subprocess.run`; record every call.

	`result` is either a CompletedProcess-like return value or an
	exception instance to raise. `lite_path=None` emulates "no
	jarvis-graph-lite checkout on this machine" (the lookup is stubbed
	to return None, so the error branch fires without any filesystem
	or subprocess activity).
	"""

	def __init__(self, result: object = None, lite_path: str | None = LITE_SRC) -> None:
		self._result = result
		self._lite_path = lite_path
		self.calls: list[tuple[list[str], dict]] = []
		self._stack = ExitStack()

	def __enter__(self) -> "_patched_backend":
		if self._lite_path is None:
			lookup = mock.patch.object(
				backend, "_find_graph_lite_path", return_value=None
			)
		else:
			lookup = mock.patch.object(
				backend,
				"_find_graph_lite_path",
				return_value=Path(self._lite_path),
			)
		self._stack.enter_context(lookup)

		def run(args: list[str], **kwargs: object) -> object:
			self.calls.append((list(args), kwargs))
			if isinstance(self._result, BaseException):
				raise self._result
			return self._result

		self._stack.enter_context(
			mock.patch.object(backend.subprocess, "run", new=run)
		)
		return self

	def __exit__(self, *exc_info: object) -> None:
		self._stack.close()


class LocateLiteCheckoutTests(unittest.TestCase):
	"""The three-step resolution order in `_find_graph_lite_path`."""

	def test_env_hint_that_exists_wins(self) -> None:
		# Rule 1: an existing JARVIS_GRAPH_LITE_PATH beats everything else.
		env = {"JARVIS_GRAPH_LITE_PATH": LITE_SRC}
		exists = _exists_only_for(LITE_SRC, _sibling_of_mcp_package(),
			"C:/JARVIS/tools/jarvis-graph-lite/src")
		with mock.patch.dict(os.environ, env, clear=True), \
			mock.patch("pathlib.Path.exists", new=exists):
			self.assertEqual(backend._find_graph_lite_path(), Path(LITE_SRC))

	def test_nonexistent_env_hint_falls_through_to_sibling(self) -> None:
		# Rule 2: the env var is only a hint — a path that does not exist
		# must not win, the sibling clone is used instead.
		sibling = _sibling_of_mcp_package()
		env = {"JARVIS_GRAPH_LITE_PATH": LITE_SRC}
		exists = _exists_only_for(sibling)
		with mock.patch.dict(os.environ, env, clear=True), \
			mock.patch("pathlib.Path.exists", new=exists):
			self.assertEqual(backend._find_graph_lite_path(), sibling)

	def test_windows_default_is_last_resort(self) -> None:
		# Rule 3 applies only when env var AND sibling both fail to exist.
		windows_default = Path("C:/JARVIS/tools/jarvis-graph-lite/src")
		env = {"JARVIS_GRAPH_LITE_PATH": LITE_SRC}
		exists = _exists_only_for(windows_default)
		with mock.patch.dict(os.environ, env, clear=True), \
			mock.patch("pathlib.Path.exists", new=exists):
			self.assertEqual(backend._find_graph_lite_path(), windows_default)

	def test_no_candidate_at_all_returns_none(self) -> None:
		with mock.patch.dict(os.environ, {}, clear=True), \
			mock.patch("pathlib.Path.exists", new=_exists_only_for()):
			self.assertIsNone(backend._find_graph_lite_path())

	def test_empty_env_hint_is_ignored(self) -> None:
		# `if env_hint:` is a truthiness check: an empty string counts as
		# unset, not as "candidate CWD", and resolution must continue.
		sibling = _sibling_of_mcp_package()
		env = {"JARVIS_GRAPH_LITE_PATH": ""}
		with mock.patch.dict(os.environ, env, clear=True), \
			mock.patch("pathlib.Path.exists", new=_exists_only_for(sibling)):
			self.assertEqual(backend._find_graph_lite_path(), sibling)


class PythonExecutableTests(unittest.TestCase):
	"""Interpreter preference in `_python_executable`."""

	def test_locatable_env_hint_is_used_verbatim(self) -> None:
		env = {"JARVIS_GRAPH_PYTHON": "py313-venv"}
		which = mock.patch("shutil.which", return_value="Q:/venvs/py313/python.exe")
		with mock.patch.dict(os.environ, env, clear=True), which:
			self.assertEqual(backend._python_executable(), "py313-venv")

	def test_unlocatable_env_hint_falls_back_to_running_interpreter(self) -> None:
		env = {"JARVIS_GRAPH_PYTHON": "definitely-no-such-python"}
		which = mock.patch("shutil.which", return_value=None)
		with mock.patch.dict(os.environ, env, clear=True), which:
			self.assertEqual(backend._python_executable(), sys.executable)

	def test_unset_env_falls_back_to_running_interpreter(self) -> None:
		with mock.patch.dict(os.environ, {}, clear=True):
			self.assertEqual(backend._python_executable(), sys.executable)


class RunGraphHappyPathTests(unittest.TestCase):
	"""What `run_graph` executes and what it returns on success."""

	def test_parsed_dict_payload_is_returned(self) -> None:
		with _patched_backend(_completed(stdout="{}")) as calls:
			result = backend.run_graph("summary", REPO)
		self.assertEqual(result, {})
		self.assertEqual(len(calls.calls), 1)

		args, kwargs = calls.calls[0]
		self.assertEqual(
			args,
			[sys.executable, "-m", "jarvis_graph", "summary", REPO, "--json"],
		)
		self.assertTrue(kwargs["capture_output"])
		self.assertTrue(kwargs["text"])
		self.assertEqual(kwargs["timeout"], 120)
		self.assertEqual(kwargs["env"]["PYTHONPATH"], str(Path(LITE_SRC)))

	def test_extra_args_are_appended_after_the_json_flag(self) -> None:
		with _patched_backend(_completed(stdout="[]")) as calls:
			result = backend.run_graph("refactor_priority", REPO, "--limit", "3")
		self.assertEqual(result, [])
		args = calls.calls[0][0]
		self.assertEqual(
			args,
			[
				sys.executable,
				"-m",
				"jarvis_graph",
				"refactor_priority",
				REPO,
				"--json",
				"--limit",
				"3",
			],
		)

	def test_parsed_list_payload_is_returned(self) -> None:
		stdout = '[{"symbol": "a"}, {"symbol": "b"}]'
		with _patched_backend(_completed(stdout=stdout)):
			result = backend.run_graph("find_dead_code", REPO)
		self.assertEqual(result, [{"symbol": "a"}, {"symbol": "b"}])

	def test_whitespace_only_stdout_yields_empty_list(self) -> None:
		# A legacy empty output must not crash JSON parsing: it maps to [].
		with _patched_backend(_completed(stdout="   \n\t")) as calls:
			result = backend.run_graph("summary", REPO)
		self.assertEqual(result, [])
		self.assertEqual(len(calls.calls), 1)

	def test_child_env_pins_pythonpath_and_keeps_ambient_vars(self) -> None:
		env = {"JG_AMBIENT_CANARY": "1", "PYTHONPATH": "STALE-VALUE"}
		with mock.patch.dict(os.environ, env, clear=True), \
			_patched_backend(_completed(stdout="{}")) as calls:
			backend.run_graph("summary", REPO)
		child_env = calls.calls[0][1]["env"]
		self.assertEqual(child_env["PYTHONPATH"], str(Path(LITE_SRC)))
		self.assertEqual(child_env["JG_AMBIENT_CANARY"], "1")

	def test_custom_python_interpreter_lands_in_argv(self) -> None:
		# The env hint itself becomes argv[0]; `shutil.which` is only a
		# gate, and its expanded path is discarded.
		hint = "py313-venv"
		env = {"JARVIS_GRAPH_PYTHON": hint}
		which = mock.patch("shutil.which", return_value="Q:/venvs/py313/python.exe")
		with mock.patch.dict(os.environ, env, clear=True), which, \
			_patched_backend(_completed(stdout="{}")) as calls:
			backend.run_graph("summary", REPO)
		self.assertEqual(calls.calls[0][0][0], hint)

	def test_timeout_default_is_120_seconds(self) -> None:
		with _patched_backend(_completed(stdout="{}")) as calls:
			backend.run_graph("summary", REPO)
		self.assertEqual(calls.calls[0][1]["timeout"], 120)

	def test_timeout_override_is_forwarded(self) -> None:
		with _patched_backend(_completed(stdout="{}")) as calls:
			backend.run_graph("summary", REPO, timeout_s=7)
		self.assertEqual(calls.calls[0][1]["timeout"], 7)


class RunGraphFailureTests(unittest.TestCase):
	"""Every error branch is converted into GraphBackendError."""

	def test_nonzero_exit_raises_with_stripped_stderr(self) -> None:
		proc = _completed(returncode=2, stdout="{}", stderr="  panic: parser exploded  ")
		with _patched_backend(proc):
			with self.assertRaises(backend.GraphBackendError) as ctx:
				backend.run_graph("summary", REPO)
		self.assertEqual(str(ctx.exception), "jarvis-graph summary failed (rc=2): panic: parser exploded")
		self.assertIsNone(ctx.exception.__cause__)

	def test_stderr_is_truncated_to_500_chars(self) -> None:
		proc = _completed(returncode=3, stdout="", stderr="y" * 700)
		with _patched_backend(proc):
			with self.assertRaises(backend.GraphBackendError) as ctx:
				backend.run_graph("summary", REPO)
		self.assertEqual(str(ctx.exception), f"jarvis-graph summary failed (rc=3): {'y' * 500}")

	def test_timeout_is_wrapped_with_command_repo_and_duration(self) -> None:
		timed_out = subprocess.TimeoutExpired(cmd=["python"], timeout=9)
		with _patched_backend(timed_out):
			with self.assertRaises(backend.GraphBackendError) as ctx:
				backend.run_graph("health_report", REPO, timeout_s=9)
		self.assertEqual(
			str(ctx.exception),
			f"jarvis-graph health_report timed out after 9s on {REPO}",
		)
		self.assertIs(ctx.exception.__cause__, timed_out)

	def test_missing_interpreter_is_wrapped_with_the_resolved_name(self) -> None:
		not_found = FileNotFoundError("no such python")
		hint = "py313-venv"
		env = {"JARVIS_GRAPH_PYTHON": hint}
		which = mock.patch("shutil.which", return_value="Q:/venvs/py313/python.exe")
		with mock.patch.dict(os.environ, env, clear=True), which, \
			_patched_backend(not_found):
			with self.assertRaises(backend.GraphBackendError) as ctx:
				backend.run_graph("summary", REPO)
		self.assertEqual(
			str(ctx.exception),
			"Python interpreter not found: py313-venv",
		)
		self.assertIs(ctx.exception.__cause__, not_found)

	def test_nonjson_stdout_is_wrapped_with_a_preview_and_cause(self) -> None:
		stdout = "ValueError: traceback tail, not JSON"
		proc = _completed(returncode=0, stdout=stdout)
		with _patched_backend(proc):
			with self.assertRaises(backend.GraphBackendError) as ctx:
				backend.run_graph("query", REPO, "auth")
		self.assertEqual(
			str(ctx.exception),
			f"jarvis-graph query returned non-JSON output: {stdout}",
		)
		self.assertIsInstance(ctx.exception.__cause__, json.JSONDecodeError)

	def test_nonjson_preview_is_capped_at_300_chars(self) -> None:
		stdout = "x" * 1000
		proc = _completed(returncode=0, stdout=stdout)
		with _patched_backend(proc):
			with self.assertRaises(backend.GraphBackendError) as ctx:
				backend.run_graph("query", REPO)
		self.assertEqual(
			str(ctx.exception),
			f"jarvis-graph query returned non-JSON output: {'x' * 300}",
		)

	def test_missing_checkout_raises_without_touching_subprocess(self) -> None:
		with _patched_backend(_completed(), lite_path=None) as calls:
			with self.assertRaises(backend.GraphBackendError) as ctx:
				backend.run_graph("summary", REPO)
		self.assertEqual(str(ctx.exception), NOT_FOUND_MSG)
		# Nothing was spawned — the failure happens before interpreter
		# resolution ever needs the filesystem.
		self.assertEqual(calls.calls, [])


class EnsureIndexedTests(unittest.TestCase):
	def test_index_command_is_run_with_defaults(self) -> None:
		recorder = mock.MagicMock(return_value={})
		with mock.patch.object(backend, "run_graph", recorder):
			backend.ensure_indexed("C:/repos/demo")
		recorder.assert_called_once_with("index", "C:/repos/demo")


class GraphBackendErrorContractTests(unittest.TestCase):
	def test_backend_error_is_a_runtime_error(self) -> None:
		# `server.py` converts only GraphBackendError into {"error": ...}
		# dicts; subclassing RuntimeError (not bare Exception) is the
		# contract that keeps unexpected failures loud.
		self.assertTrue(issubclass(backend.GraphBackendError, RuntimeError))


if __name__ == "__main__":
	unittest.main()
