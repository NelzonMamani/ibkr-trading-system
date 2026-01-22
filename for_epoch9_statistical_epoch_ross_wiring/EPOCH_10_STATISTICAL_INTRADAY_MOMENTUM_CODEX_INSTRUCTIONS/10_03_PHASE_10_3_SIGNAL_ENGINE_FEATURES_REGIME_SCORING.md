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


## Phase 10.3 Objective
Implement the signal engine that converts context into a momentum score and then into canonical intents.
No orchestrator wiring. No broker interactions.

## Allowed Files
- `src/strategies/statistical_intraday_momentum/signal_engine/features.py`
- `src/strategies/statistical_intraday_momentum/signal_engine/regime.py`
- `src/strategies/statistical_intraday_momentum/signal_engine/scoring.py`
- `src/strategies/statistical_intraday_momentum/signal_engine/signal_decision.py` (create)
- tests

## Minimal Context Contract
Accept a minimal dict-like snapshot:
- `symbol`
- `now_ts`
- `bars_1m` / `bars_5m` (OHLCV lists)
- `last_price`
- `day_volume`
- `spread_pct` (optional)
- `minutes_since_open` or `session_phase` (optional)

Missing fields => DISALLOW/NO_TRADE + reasons.

## Feature Set (v1)
- returns: 1m, 5m, 15m
- realized volatility proxy: stddev of 1m returns over 15m (or ATR proxy)
- volume acceleration: last 5m volume vs prior 5m
- persistence: fraction of positive 1m returns over last N

## Regime Gate
Trade only when:
- volatility in [floor, ceiling]
- liquidity above floor
- spread below ceiling (if provided)
- within allowed time window

## Scoring & Intent
- `momentum_score` = weighted sum of drift + persistence + volume_accel
- ENTER_LONG if score >= enter_threshold and regime ALLOW
- HOLD if in position and score >= hold_threshold
- EXIT_ONLY if in position and (score < exit_threshold or regime DISALLOW)
- NO_TRADE otherwise

## Implementation Steps
1. Implement pure feature functions in `features.py`.
2. Implement `evaluate_regime(...)` in `regime.py` returning AllowState + reasons.
3. Implement `compute_score(...)` in `scoring.py` returning score + diagnostics.
4. Implement `decide_intent(...)` in `signal_decision.py` returning DecisionIntent / SignalIntent.
5. Ensure determinism (no randomness).

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
