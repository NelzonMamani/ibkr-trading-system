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


## Phase 10.2 Objective
Implement `strategy_policy.py` for Statistical Intraday Momentum, written **directly to the Epoch 9 interface types**.

## Allowed Files
- `src/strategies/statistical_intraday_momentum/strategy_policy.py`
- tests (as needed)

## Policy Requirements
1. Use dataclasses (frozen=True) for policy specs.
2. Use Epoch 9 contract types from `src/strategy_portfolio/contracts.py` and reason codes.
3. Heavily comment all parameters: what they do, why conservative, what tuning would mean.
4. Conservative defaults (prefer NO_TRADE over false positives).

## Minimum Policy Sections (Must Exist)
- Identity: `name`, `version`
- Universe: price bounds, volume/liquidity floor, spread ceiling (if available), allowed sessions
- Activation: explicit time windows, cooldown controls
- Regime: volatility floor/ceiling, liquidity/spread gates
- Signal: lookbacks, confirmation, thresholds for enter/hold/exit
- Risk: per-trade risk request, stop model choice, max concurrent positions request
- Telemetry: enable/disable learning-only outputs

## Suggested Initial Parameter Ranges (Conservative)
Include these in comments and as defaults where reasonable:
- Price range: $5–$200 (avoid microcap noise in v1)
- Min dollar volume: $20M/day (or min share volume equivalent)
- Vol floor: realized vol proxy above ~0.5%–1.0% over 15m
- Vol ceiling: disallow extreme volatility spikes (configurable)
- Lookbacks: 5m and 15m returns; confirmation 1m–3m persistence
- Cooldown: 60–180 seconds per symbol
- Long-only: True default

## Implementation Steps
1. Create `strategy_policy.py` with top-level dataclass `StatisticalIntradayMomentumPolicy` and nested specs:
   - `UniverseSpec`, `ActivationSpec`, `RegimeSpec`, `SignalSpec`, `RiskSpec`, `TelemetrySpec`
2. Provide helper functions:
   - `policy_identity(policy) -> StrategyIdentity`
   - `default_policy() -> StatisticalIntradayMomentumPolicy`
3. Ensure no imports from Ross modules.

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
