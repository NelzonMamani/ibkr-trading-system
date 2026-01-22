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


## Phase 10.4 Objective
Implement `risk_policy.py` that outputs risk requests and constraints (policy-level only).

## Allowed Files
- `src/strategies/statistical_intraday_momentum/risk_policy.py` (create)
- tests

## Requirements
- Dataclasses describing:
  - per-trade risk request (USD or pct)
  - stop distance model (sigma/ATR multiple)
  - max concurrent positions requested
  - optional strategy daily loss limit request
- Conservative defaults.
- Missing data => disabled request + reasons.

## Implementation Steps
1. Create `risk_policy.py` with `RiskRequest` and `StopModelSpec`.
2. Implement `build_risk_request(policy, context, symbol) -> RiskRequest`.
3. Unit tests for missing data and deterministic outputs.

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
