# Epoch 9 — Strategy Portfolio Governance (Codex Implementation Instructions)
Date: 2026-01-22

## Non‑Negotiable Constraints (Global)
1. DO NOT modify any files under:
   - `src/strategies/ross_momentum/**`
   - any file named `strategy_policy.py` inside `ross_momentum`
2. DO NOT modify the existing orchestrator behaviour or flow yet.
   - No edits to `src/core/orchestrator.py` (or equivalent orchestrator module) in this epoch.
3. This epoch is **infrastructure-only**:
   - Add new modules/classes/tests that will later be wired in.
   - Ensure they are importable and testable in isolation.
4. No changes to scanner logic, execution logic, or risk engine logic.
5. All new code must be additive and safe to ignore until wired later.

## Mandatory Verification Commands (Must Pass)
Run these commands at the end of each phase (and fix any failures immediately):
1. `python -m compileall -q src`
2. `python -m pytest -q`
If the repo contains additional mandatory checks already used in CI (e.g., ruff/mypy), run them too,
but do not introduce new tooling requirements in this epoch.


## Phase 9.6 Objective
Add explicit guardrails so the Epoch 9 implementation cannot accidentally drift into modifying Ross or orchestrator.

These guardrails are implemented as:
- documentation +
- tests that assert forbidden files were not modified in this epoch’s PR (where feasible) + 
- runtime import isolation tests

## Allowed Files
- `tests/strategy_portfolio/test_non_interference.py`
- `EPOCH_09_*` docs (in repository) — if your repo stores epoch docs
- No production code changes beyond Epoch 9 package

## Implementation Steps
1. Add `tests/strategy_portfolio/test_non_interference.py`
   - Ensure importing `src/strategy_portfolio/*` does not import:
     - `src/strategies/ross_momentum/*`
     - orchestrator module
   - (Use `sys.modules` inspection and importlib to validate minimal imports.)
2. Add a small “forbidden paths” note in epoch docs (if stored in repo).
3. Verify tests pass.

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
