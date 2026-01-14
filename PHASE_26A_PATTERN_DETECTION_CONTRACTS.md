# PHASE_26A_PATTERN_DETECTION_CONTRACTS

## Objective
Freeze the **Pattern Detection contracts** so each pattern is deterministic, testable, and explainable.

## Scope
### In-Scope
- Canonical datamodels:
  - `PatternInputs`
  - `PatternResult`
- Enums/constants:
  - `PatternFamily` (GAP/OPEN, BREAKOUT, PULLBACK, REVERSAL, RANGE, VOL_EVENT, CANDLE)
  - `Direction` (LONG/SHORT/NEUTRAL)
- Standard print/log convention for detected vs rejected patterns
- Data-quality conventions (`data_quality_flags`, missing indicator handling)

### Out-of-Scope
- Implementing full pattern logic (begins in Phase 26B/26C)
- Any Risk or Execution behaviour

## Canonical Contracts
### PatternInputs (minimum)
- `symbol`
- `timeframe` (e.g. 10s, 1m, 5m)
- `candles` (OHLCV)
- `session_context` (PRE/REGULAR/AFTER)
- `levels` (premarket high/low, HOD/LOD, prior close, key S/R)
- `indicators` (EMA set, VWAP; MACD optional)
- `liquidity_context` (spread, float, RVOL)
- `news_context` (optional)
- `data_quality_flags` (list)

### PatternResult (required)
- `pattern_name`
- `pattern_family`
- `detected` (bool)
- `direction`
- `confidence` (0.0–1.0)
- `setup_quality_tags` (list)
- `entry_zone` (optional)
- `stop_suggestion` (optional)
- `target_suggestion` (optional)
- `rationale_text`
- `risk_flags` (list)

## Standard Print Contract
- Detected:
  - `[PATTERN] <symbol> <pattern_name> DETECTED <direction> conf=<x.xx>`
  - Followed by 2–5 rationale lines (levels, volume/indicator alignment)
- Rejected:
  - `[PATTERN] <symbol> <pattern_name> not detected (reason=<short>)`

## Files to Create/Modify (Repo)
- Create: `src/strategies/ross_momentum/patterns/pattern_types.py`
- Create: `src/strategies/ross_momentum/patterns/pattern_base.py`
- Create: `src/strategies/ross_momentum/patterns/pattern_inputs.py`

## Definition of Done
- All patterns can share the same input/output schema.
- A unit test can instantiate `PatternInputs` and validate `PatternResult` shape without IBKR.
- Missing data is surfaced explicitly, not hidden.
