# 001 — pyproject.toml pip-depended on an unpublished package

## Task

Ship v0.1.0 of `jarvis-graph-mcp` to GitHub so anyone running
an MCP client (Claude Desktop, Claude Code, Cursor,
Windsurf, Cline) can `pip install git+…/jarvis-graph-mcp` and
have a working code-intelligence server pointed at their local
sibling clone of `jarvis-graph-lite`.

## What failed

`pyproject.toml`'s `dependencies` list included:

```toml
dependencies = [
    "mcp>=1.0.0",
    "jarvis-graph-lite>=0.12.4",
]
```

`jarvis-graph-lite` is the backend that provides the
code-intelligence engines. It lives at
`github.com/Zilli-on/jarvis-graph-lite` but is **not
published to PyPI** (stdlib-only tool, distributed as a
git clone, not a pip package).

The `pip install` attempt therefore failed at the
dependency-resolution step for any user on a fresh machine
who cloned or `pip install git+…`'d the repo:

```
ERROR: Could not find a version that satisfies the
requirement jarvis-graph-lite>=0.12.4
ERROR: No matching distribution found for jarvis-graph-lite>=0.12.4
```

The installer is technically doing the right thing — the
registry has no such package. Our declaration was lying about
the install contract.

## Root cause

Misreading the relationship between `mcp` and `lite`. `mcp`
does NOT import from `lite`. It **invokes** lite as a
subprocess, discovering its source path at runtime via three
fallback rules:

1. `JARVIS_GRAPH_LITE_PATH` env var (absolute path)
2. Sibling clone at `../jarvis-graph-lite/src`
3. Windows default `C:\JARVIS\tools\jarvis-graph-lite\src`

See `src/jarvis_graph_mcp/backend.py:_locate_lite_src`.

The correct model: runtime-discovered sibling, not
pip-declared dependency. Declaring it as a pip dep was both
wrong (the relationship is subprocess, not import) AND broken
(the registry can't resolve it).

## Fix

Commit `64da662` (landed in PR #1, `fix/remove-pip-dep-on-lite`
→ `main`): drop `jarvis-graph-lite>=0.12.4` from
`pyproject.toml` `dependencies`, replace with an explanatory
comment block that documents the three-rule discovery contract.

## Prevention rule

1. **Run `pip install .` (or `-e .`) in a fresh virtualenv
   before tagging a release.** A PyPI-registry install path
   must actually resolve. The v0.1.0 tag shipped without this
   check.
2. **CI must exercise the install path strangers see.** The
   GitHub Actions workflow added in PR #2 does exactly this:
   fresh runner, fresh Python, `pip install -e .`, then
   import + smoke. Any future regression of this pattern
   surfaces in the PR, not in the first user's bug report.
3. **Runtime discovery ≠ pip dependency.** If the
   relationship is subprocess-based or
   plugin-discovered, it does NOT belong in `pyproject.toml`
   `dependencies`. Dependencies are for `import` relationships.

## See also

- Commit `64da662` (fix) in PR #1
- `.github/workflows/ci.yml` (added in PR #2) — the install-
  path regression guard
- `src/jarvis_graph_mcp/backend.py` `_locate_lite_src` — the
  three-rule discovery code path
- `README.md` "Install" section — the user-facing install
  contract that was under-specified before this incident
