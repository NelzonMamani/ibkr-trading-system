# PHASE_26B_ROSS_CORE_PATTERN_IMPLEMENTATION

## Objective
Implement the **Ross Momentum core pattern set** (Phase 1 priorities) using the frozen contracts from Phase 26A.

Core patterns (implement in this order):
1) Premarket High Break
2) Opening Range Breakout (ORB)
3) Micro Pullback (1–3 bars)
4) Bull Flag
5) Consolidation Breakout
6) Failed Breakout (caution / exit signal)

## Guardrails
- Candlestick patterns are not triggers here; they are evidence tags.
- Each pattern must return `detected=False` with a rejection reason if not valid.
- Patterns must be deterministic and explainable.

## Required Inputs
- 10s and 1m candles (minimum); 5m optional for confirmation
- VWAP and EMA9/20 (EMA50/200 optional)
- Levels: premarket high/low, HOD/LOD
- Liquidity: spread, RVOL, float context

## Output Expectations
- For each symbol evaluated, produce `PatternResult` objects for enabled patterns
- Print detected/rejected with teacher-style rationale

## Files to Create/Modify (Repo)
- Create: `src/strategies/ross_momentum/patterns/momentum_patterns.py`
- Create: `src/strategies/ross_momentum/patterns/breakout_patterns.py`
- Create: `src/strategies/ross_momentum/patterns/reversal_patterns.py`
- Create: `src/strategies/ross_momentum/patterns/pattern_registry.py` (enabled set for Ross)

## Definition of Done
- Running the Ross pattern registry on a mocked symbol produces:
  - a stable list of `PatternResult`s
  - at least one detected pattern in known test fixtures
  - clear rejection reasons when not detected
- Core patterns operate without IBKR execution and without mutable global state.
