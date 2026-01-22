# Epoch 10 — Statistical Intraday Momentum (Codex Implementation Instructions)
Date: 2026-01-22

## Global Constraints (Non-Negotiable)
1. DO NOT modify any files under:
   - `src/strategies/ross_momentum/**`
2. DO NOT modify orchestrator flow yet:
   - No edits to `src/core/orchestrator.py` (or equivalent orchestrator module) in this epoch.
3. DO NOT modify scanner logic, execution logic, or global risk engine logic.
4. This epoch must be **additive**:
   - Only add the new strategy module and its tests.
   - Strategy must compile and be testable in isolation.
5. Strategy must be **interface-native**:
   - It must use the Epoch 9 governance types in `src/strategy_portfolio/*` (contracts, reason codes, etc.)
6. Strategy must not require new third-party dependencies.
7. Provide comments in all policy/config sections explaining intent and safe defaults.

## Mandatory Verification Commands (Must Pass)
Run at the end of each phase (and fix failures immediately):
1. `python -m compileall -q src`
2. `python -m pytest -q`

If repo already has existing required checks (ruff/mypy), run them too,
but do not add new tool requirements in this epoch.


## Phase 10.6 Objective
Build tests proving interface compliance, safety defaults, determinism, and no Ross imports.

## Allowed Files
- `tests/strategies/statistical_intraday_momentum/*`

## Required Tests
- `test_policy_imports.py` (imports succeed; no Ross imported)
- `test_contract_compliance.py` (uses Epoch 9 contract types)
- `test_safe_defaults.py` (missing context => DISALLOW/NO_TRADE + reasons)
- `test_scoring_determinism.py` (identical inputs => identical outputs)
- `test_regime_gates.py` (vol/liquidity/time gating works)
- `test_end_to_end_smoke.py` (fake bars => plausible intent path)

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
