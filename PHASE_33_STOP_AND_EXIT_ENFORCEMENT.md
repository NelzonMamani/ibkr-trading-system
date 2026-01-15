# PHASE_33_STOP_AND_EXIT_ENFORCEMENT.md
# PHASE 33 — STOP & EXIT ENFORCEMENT (AUTHORITATIVE)

## 0. Purpose
Ensure that when execution is enabled (SIM / LIVE_MICRO / LIVE), the system:
- Places and respects stop-loss logic
- Enforces exit precedence deterministically
- Closes trades when exit conditions are met
- Never allows “strategy discretion” to override safety exits

## 1. Exit precedence (hard rule)
Exit precedence order is:

1) **Emergency / circuit breaker kill-switch** (Phase 34)  
2) **Stop-loss / hard risk stop**  
3) **RiskEngine exit veto / downgrade**  
4) **Strategy-driven exits**  
5) **Time-based exits** (if configured)  

No lower-priority exit may override a higher-priority exit.

## 2. Stop-loss model (Epoch 3 minimum)
Epoch 3 introduces a canonical stop-loss model that can be simple but must exist.

Minimum requirements:
- Stops are derived from intent stop_model / structure language (Epoch 2 output)
- If stop_model is not parseable, default to a conservative stop policy:
  - SIM: fixed % stop (configurable)
  - LIVE_MICRO/LIVE: must be conservative and explicit

Stop placement and stop updates must be logged and persisted.

## 3. TradeExitEngine responsibilities
TradeExitEngine must:
- Track open trades and associated protective stops
- Evaluate stop triggers from market data (SIM feed or live snapshots)
- Emit deterministic exit orders (or simulated exits) when triggered
- Persist TradeOutcome records and update PerformanceRegistry

## 4. Required code touchpoints (expected)
- `src/execution/trade_exit_engine.py`
- `src/execution/exit_plan.py`
- `src/core/active_trade_registry.py`
- `src/core/trade_outcome_factory.py`
- Existing tests: `tests/test_exit_precedence.py` (extend), plus new stop enforcement tests

## 5. Required tests (minimum)
1. Stop-loss exits occur even if strategy says “hold”
2. Circuit breaker exit overrides stop/strategy exits (Phase 34 integration)
3. Exit precedence ordering is deterministic and tested
4. Trade outcomes are persisted and reflected in performance snapshot

## 6. Acceptance criteria
Phase 33 is complete when:
- Protective stop behavior exists in SIM and can be enabled in LIVE_MICRO/LIVE
- Exit precedence is enforced by tests
- Trade outcomes and performance snapshots reflect stop exits correctly
- Logs and events clearly show why an exit happened

---
End of PHASE_33_STOP_AND_EXIT_ENFORCEMENT.md
