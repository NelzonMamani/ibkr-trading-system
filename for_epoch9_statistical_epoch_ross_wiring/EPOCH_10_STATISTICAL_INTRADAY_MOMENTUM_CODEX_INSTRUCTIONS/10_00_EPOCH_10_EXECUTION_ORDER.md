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


## Purpose of This File
This is the authoritative order-of-operations for implementing Epoch 10.
Codex must implement phases strictly in order, running Mandatory Verification Commands after each phase.

## Phase Order
- Phase 10.1 — Strategy Scope & Assumptions (docs + design skeleton)
- Phase 10.2 — Strategy Policy (interface-native `strategy_policy.py`)
- Phase 10.3 — Signal Engine (features + regime gating + scoring)
- Phase 10.4 — Risk Policy (risk requests + position sizing intent)
- Phase 10.5 — Telemetry (learning-only outputs; no trading effects)
- Phase 10.6 — Tests & Validation Suite (contract compliance + no-Ross imports + determinism)

## New Strategy Location (Create)
- `src/strategies/statistical_intraday_momentum/`
- `tests/strategies/statistical_intraday_momentum/`

## Definition of Done (Epoch 10)
- Strategy folder exists with clean structure and docstrings.
- `strategy_policy.py` is interface-native and heavily commented.
- Signal engine produces deterministic intents given deterministic context.
- Strategy contains explicit activation windows and regime gates (volatility, liquidity, time-of-day).
- Tests prove:
  - Contract compliance
  - Safe defaults (DISALLOW/NO_TRADE when inputs missing)
  - No imports from Ross modules
  - Deterministic outputs
- Mandatory Verification Commands pass.
