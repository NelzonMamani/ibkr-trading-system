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


## Phase 10.1 Objective
Create the strategy module skeleton and document the scope, assumptions, and research-backed design principles.
No trading wiring. No orchestrator edits.

## Research Anchors (Use as design justification; do not overfit)
Documented empirical themes relevant to intraday statistical momentum include:
- Intraday momentum/time-series momentum effects in markets and intraday intervals.
- Time-of-day effects and periodicity (open/close are structurally different).
- Intraday volatility periodicity and persistence; models should condition on time-of-day and volatility regimes.

Example sources include research on:
- First half-hour return predicting late-day return patterns (market intraday momentum).
- Intraday time-series momentum evidence across markets.
- Intraday volatility periodicity/persistence in high-frequency returns.

## Deliverables (This Phase)
Create these files under `src/strategies/statistical_intraday_momentum/`:
- `__init__.py`
- `README.md`
- `strategy_assumptions.md`

Create package stubs:
- `signal_engine/__init__.py`
- `signal_engine/features.py`
- `signal_engine/regime.py`
- `signal_engine/scoring.py`

## Scope (Authoritative for Epoch 10)
This strategy is **Statistical Intraday Momentum**, meaning:
- It trades short-horizon continuation **when behaviour is stable**
- It refuses to trade in volatility collapse or microstructure-chaos regimes
- It is probability/threshold driven (no pattern engine)
- It is initial-rule-based (no ML dependency required)

## Explicit Non-Goals
- Not HFT: no sub-millisecond assumptions; no queue-position dependence.
- Not mean reversion (separate epoch).
- No short-selling required for v1: implement long-only by default, keep structure extensible.

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
