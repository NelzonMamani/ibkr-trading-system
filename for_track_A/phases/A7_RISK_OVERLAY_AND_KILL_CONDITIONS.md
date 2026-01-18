# A7 — Risk overlay & kill conditions

## Intent
Guarantee safety: daily max loss, circuit breakers, halts, volatility spikes, topping-tail pause cascade, operator kill-switch.

## Scope
Risk engine + stop controller + strategy-level pause/stop flags.

## Required Outputs (Files / Modules)
- `src/risk/risk_engine.py`
- `src/core/stop_controller.py`
- `src/strategies/ross_momentum/ross_momentum_risk_overlay.py`

## Implementation Steps (Codex must follow exactly)
1. Ensure global kill switch blocks all submissions in PAPER and LIVE modes.
2. Add/confirm Ross-specific kill conditions: consecutive losses, drawdown limit, abnormal spread, halt detection, excessive slippage, topping-tail cascade.
3. Integrate with stop_controller so STOP_TRADING_DAY latches and requires manual reset.
4. Add tests verifying risk engine blocks even if strategy emits intents.

## Definition of Done (DoD)
- Risk engine is final gate and blocks all intents when tripped.
- Kill conditions latch and require manual reset.
- All tests pass.

## Validation Commands
- `pytest -q`
