# Restructure Plan (No-breaking order)

Codex must follow this safe order:

## Step A — CLI correctness (small, low-risk)
- Ensure every CLI tool is runnable as a module:
  - prefer `python -m src.cli.submit_one_order --help`
- Fix any `ModuleNotFoundError: No module named 'src'` by:
  - using module invocation
  - and/or adding proper `if __name__ == "__main__"` entry points
  - and/or ensuring `src/cli/__init__.py` exists (already does)

## Step B — Boundary shims (compatibility)
- If any imports reference legacy paths, add re-export modules rather than mass-breaking moves.
- Prefer creating small `src/<old_pkg>/__init__.py` re-exports that import from new canonical location.

## Step C — Move only if needed
- Do not move large directories unless the benefit is strong and tests remain stable.
- If moving, do it in small batches and run:
  - `python -m compileall src`
  - `pytest -q`

## Step D — Git hygiene (shedding support)
- Ensure `data/`, `output/`, `logs/` are treated as runtime-generated:
  - add/update `.gitignore` if needed
- Ensure tests create temp DBs or use fixtures, not committed DB files.

Deliverable: `AUDIT_EVIDENCE/E25_migration_plan.md` summarizing what changed and why.
