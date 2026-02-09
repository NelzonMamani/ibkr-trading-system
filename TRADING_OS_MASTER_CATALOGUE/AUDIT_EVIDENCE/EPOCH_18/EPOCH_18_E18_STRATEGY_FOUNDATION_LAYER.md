# EPOCH 18 — Strategy Foundation Layer (E18)

## Summary
E18 establishes the shared, deterministic strategy foundation catalogue, candlestick primitives, and context hydration utilities required for strategy policies without imposing strategy-specific logic.

## Scope
- `src/strategies/common/foundation.py`
- `src/strategies/common/candles/single_candle.py`
- `src/strategies/common/candles/multi_candle.py`
- `src/strategies/common/candles/functional.py`
- `src/strategies/common/candles/contextual_states.py`
- `tests/strategies/test_candlestick_foundation.py`
- `tests/strategies/test_foundation_catalogue.py`

## Evidence
Command outputs are captured in this folder:
- `python -m compileall src tests` → `compileall.txt`
- `pytest tests/strategy_portfolio tests/strategies tests/test_ross_strategy_registry.py tests/test_strategy_registry_epoch13.py tests/smoke` → `pytest.txt`

## Notes
- Foundation primitives remain policy-neutral and are not wired into live trading flows.
