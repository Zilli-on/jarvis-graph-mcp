"""
pytest bootstrap for the src-layout package.

Without this file, `python -m pytest` fails with
`ModuleNotFoundError: No module named 'jarvis_graph_mcp'`
unless the user has first run `pip install -e .`. That is a
surprise for anyone cloning the repo fresh — especially since
the CI workflow hides the problem by running `pip install -e .`
explicitly before pytest (see `.github/workflows/ci.yml`).

This conftest makes `src/` discoverable at test-time so the
common path (`git clone`, `python -m pytest`) Just Works. Pip
install is still the right install path for end users; this
file is about the test-dev ergonomic.

Root cause documented in failures/001 is a sibling: that was
an install-contract bug (pip dep on unpublished package). This
is the test-run-contract counterpart — same family of
"install-path surprise" issues. Both are prevented by CI +
by this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Prepend the src directory so imports of `jarvis_graph_mcp`
# resolve whether or not `pip install -e .` has been run.
SRC = Path(__file__).resolve().parent.parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
