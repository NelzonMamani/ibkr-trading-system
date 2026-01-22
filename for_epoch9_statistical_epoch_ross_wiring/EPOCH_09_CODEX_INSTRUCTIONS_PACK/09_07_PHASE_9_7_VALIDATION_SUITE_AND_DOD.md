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


## Phase 9.7 Objective
Provide a validation suite demonstrating that Epoch 9 is:
- additive
- deterministic
- safe by default
- ready to host future strategies (Statistical Intraday Momentum) without wiring changes

## Allowed Files
- `tests/strategy_portfolio/*`
- No production edits beyond `src/strategy_portfolio/*`

## Implementation Steps
1. Add `tests/strategy_portfolio/test_end_to_end_smoke.py`
   - Construct a fake interface-native strategy policy object (simple dataclass) with:
     - identity
     - activation allow flag
   - Pass a fake context snapshot
   - Confirm normaliser outputs ALLOW/ENTER (only if explicit)
   - Confirm arbitration resolves deterministic winner
   - Confirm allocation assigns budgets deterministically

2. Ensure all modules have docstrings and are importable.

## Definition of Done (Epoch 9)
- `src/strategy_portfolio/` exists with contracts/registry/arbitration/allocation/normaliser/reason_codes
- Test suite exists under `tests/strategy_portfolio/`
- Mandatory Verification Commands pass
- No changes to Ross or orchestrator modules
