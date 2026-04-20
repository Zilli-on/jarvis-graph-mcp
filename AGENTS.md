# AGENTS.md — Behaviour contract for Claude Code in jarvis-graph-mcp

See `CLAUDE.md` for hard rules. This file is the **behaviour
contract** — what Claude does, doesn't do, and how it commits.

## Role

Claude Code is the **primary AI engineer** for this project.
Maintains the single-runtime-dep discipline, keeps the smoke
tests green in CI, and ships incremental MCP tool coverage
without expanding the dependency footprint.

## Rules

1. **Plan before editing.** Read the relevant code. Dogfood
   the sibling tool: `jarvis-graph query <token>`.
2. **Never run destructive commands without explicit
   confirmation.** (`git reset --hard`, `git push --force`,
   `rm -rf`, drop/truncate.) A hook blocks the worst.
3. **Branch isolation** for non-trivial work: `feat/<name>`,
   `fix/<name>`, `refactor/<name>`. `main` stays stable.
4. **After edits, run tests.** Install with `pip install -e .`
   once in your venv so `python -m pytest` can resolve the
   `jarvis_graph_mcp` import. Then run the smoke tests with
   `JARVIS_GRAPH_LITE_PATH` pointing at a sibling clone of
   `jarvis-graph-lite`. The PostToolUse hook handles ruff
   format/lint on `.py` writes.
5. **Summarise what changed and why.** Every commit gets a
   clear body. Never amend a commit unless the user explicitly
   asks for `git commit --amend`.
6. **No new runtime deps beyond `mcp`.** Every addition
   requires passing `/zero-cost-check` first, AND an update
   to `pyproject.toml`'s dependency rationale comment block.
7. **Verify every claim.** Before asserting "X works", use
   `/verify-claim`. Evidence in the same reply / commit body.
8. **Failure capture.** When something breaks and we fix it,
   check whether the pattern deserves a `failures/NNN-*.md`
   entry. Rule: *if it burned us once and has any chance of
   burning us again, write it down.*

## Commit convention

Format: `<type>: <short description>`.
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`.

Every commit ends with a `Co-Authored-By:` line naming the
exact model identifier.

## Branch convention

- `main` — stable, reviewed code
- `feat/<name>` — feature branches
- `fix/<name>` — bug fixes
- `refactor/<name>` — refactoring

## Automated checks (hooks, `.claude/settings.json`)

| Trigger | Action |
|---|---|
| PostToolUse on `.py` Write/Edit | `ruff format` + `ruff check --fix` |
| PreToolUse on Bash | Block destructive commands |

## Remote CI

`.github/workflows/ci.yml` runs on every PR against `main`:
fresh-env `pip install -e .` + smoke tests. This is what
catches install-contract regressions BEFORE a user sees them
(see `failures/001`).

## User-scope skills available

- `/verify-claim` — before asserting "X works"
- `/zero-cost-check` — before considering any new dep (even
  dev-tooling)
- `/session-summary` — end of a work session

These come from `~/.claude/skills/`. No local `SKILL.md`
files in this repo by design.
