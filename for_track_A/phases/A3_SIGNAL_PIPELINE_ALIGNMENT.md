# A3 — Signal pipeline alignment (scanner → signals → Ross inputs)

## Intent
Ensure scanner output can be transformed into Ross policy inputs (key levels, HOD/PMH, VWAP/EMAs/MACD, RVOL).

## Scope
Adapters and feature calculation only.

## Required Outputs (Files / Modules)
- `src/market_data/market_data_hub.py (or canonical feed module)`
- `src/strategies/ross_momentum/patterns/pattern_inputs.py`
- `src/strategies/ross_momentum/patterns/pattern_evaluator.py`

## Implementation Steps (Codex must follow exactly)
1. Define a canonical per-symbol feature view providing 10s and 1m candles, volumes, VWAP, EMAs(9/20/50/200), MACD histogram, HOD, and premarket high.
2. Implement an adapter that builds this from the live market data hub (SIM can use replay feed).
3. Ensure watchlist symbols are subscribed for required data resolutions (10s, 1m, 5m) without blocking the orchestrator loop.
4. Add tests using fixtures to assert deterministic feature calculations.

## Definition of Done (DoD)
- For any symbol in watchlist, required features for Ross policy are available within bounded time.
- No silent missing-field fallbacks in live path.
- All tests pass.

## Validation Commands
- `pytest -q`
