# failures/

Catalogue of failure patterns we have hit in jarvis-graph-mcp.
The root cause, the fix, and the rule added to prevent
recurrence.

Project memory for the rakes we've already stepped on.

## Rule for what goes here

*"If it burned us once and has any chance of burning us
again, write it down."*

DO add:
- an install-path regression (the canonical case — see 001)
- a protocol/schema change that silently breaks a client
- a platform / shell / language gotcha
- a hard rule we violated that the linter doesn't catch

Do NOT add:
- one-off typos
- transient network hiccups
- library bugs already fixed upstream

## File format

`failures/NNN-<short-slug>.md` — monotonic 3 digits, never
reused. Slug kebab-case, ≤ 6 words.

Each file: five sections (Task / What failed / Root cause /
Fix / Prevention rule).

## Index

| # | Title | Discovery |
|---|---|---|
| 001 | pyproject.toml pip-depended on an unpublished package | 2026-04-15, `pip install` against PyPI against a fresh env |
