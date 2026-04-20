# jarvis-graph-mcp

Local-first code-intelligence MCP server. Exposes
`jarvis-graph-lite`'s 17 code-intelligence commands (+ 1
health aggregate) as 18 MCP tools to any MCP client — Claude
Desktop, Claude Code, Cursor, Windsurf, Cline. Python 3.11+.

Product identity: **local-first**. Your source never leaves
your machine. No telemetry. No cloud. No API costs.

## Hard rules

1. **One runtime dep max (`mcp` PyPI package, MIT, Anthropic
   PBC).** `jarvis-graph-lite` is invoked as a subprocess
   (path-discovered at runtime), NOT as a pip dependency —
   declaring it as one would break `pip install` against a
   registry where lite is not yet published. See
   `failures/001-pip-install-unpublished-dep.md` for the
   canonical incident.
2. **Python 3.11+ minimum.** Aligns with `mcp`'s stated
   minimum. Classifiers advertise 3.11 + 3.12.
3. **No fake certainty.** Before claiming "X works", verify.
   Use the `/verify-claim` user-scope skill.
4. **Branch isolation.** Non-trivial work on `feat/*`,
   `fix/*`, `refactor/*`. `main` stays stable.
5. **MIT-compatible licences only.** Project is MIT. Any dep
   considered must be MIT / Apache-2.0 / BSD / public-domain.
6. **Local-first discovery contract for `jarvis-graph-lite`.**
   Three resolution rules in order:
   1. `JARVIS_GRAPH_LITE_PATH` env var (absolute path)
   2. Sibling clone at `../jarvis-graph-lite/src`
   3. Windows default `C:\JARVIS\tools\jarvis-graph-lite\src`
   Documented in `README.md`'s "Install" section. Any change
   to this contract lands as a documented breaking change.

## Where things go

| Need | Goes to |
|---|---|
| Broadly applicable rule | this file |
| Behaviour contract | `AGENTS.md` |
| Deterministic automation | `.claude/settings.json` hooks |
| Failure patterns | `failures/NNN-*.md` |
| Release notes | (not yet — add `CHANGELOG.md` at v0.2.0) |
| Architecture | `docs/` |

## Inherited skills (user-scope)

`/verify-claim`, `/zero-cost-check`, `/session-summary` live
at `~/.claude/skills/` and are available here without a local
`SKILL.md`. Disciplines live upstream in the
`CLAUDE.MD` meta-workspace; behaviour-contract lives here.
