# A6 — Per-symbol trade loop & re-entry controls

## Intent
Allow Ross-style repeated in/out entries on the same symbol while preventing runaway behaviour and keeping explainability.

## Scope
Trade counting, cooldowns, re-entry windows, per-symbol governance.

## Required Outputs (Files / Modules)
- `src/core/active_trade_registry.py`
- `src/strategies/ross_momentum/strategy_policy.py`
- `src/strategies/ross_momentum/decision_policy.py`

## Implementation Steps (Codex must follow exactly)
1. Replace arbitrary `max_trades_per_symbol` with a tunable parameter designed for micro pullback loops (default high enough, enforced by permission matrix and risk).
2. Implement cooldown after hard-exit reasons (e.g., failed breakout) before re-entry unless new HOD reclaim occurs.
3. Add counters to context: trades_this_symbol, last_entry_time, last_exit_reason, consecutive_losses_this_symbol.
4. Enforce `TRADE_PERMISSION_MATRIX` states: ALLOW, PAUSE, BLOCK_SYMBOL, STOP_DAY.
5. Add tests for multiple valid re-entries and for blocked re-entry after failure.

## Definition of Done (DoD)
- System can perform multiple micro pullback re-entries in SIM fixtures without violating risk overlay.
- Permission matrix blocks correctly after defined failure conditions.
- All tests pass.

## Validation Commands
- `pytest -q`
