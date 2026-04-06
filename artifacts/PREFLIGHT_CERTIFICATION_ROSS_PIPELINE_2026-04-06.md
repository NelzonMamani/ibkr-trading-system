# Preflight Certification — Ross pipeline and paper execution path

Date: 2026-04-06 (UTC)

## Runtime path in use
- The continuous runtime CLI (`src/cli/run_trading_loop.py`) calls `src.core_engine.orchestrator.run_cycle(...)`.
- Therefore this certification treats `src/core_engine/orchestrator.py` + `src/execution/order_router.py` as the PAPER runtime path.

## Structural findings
1. **Scanner → watchlist/focus → setup/trigger/intent is wired** in `run_cycle`:
   - scanner payload via `run_scanner_cycle`
   - watchlist/focus derivation
   - per-focus `PatternEvaluator`
   - `build_trade_intents`
   - `evaluate_trade_intents`
   - `execute_intents`

2. **RossMomentumStrategyV1 is not on this core_engine runtime path.**
   - `core_engine/orchestrator.py` imports and uses `build_trade_intents` from `src/strategies/ross_momentum/decision_policy.py`.
   - `RossMomentumStrategyV1` is used by `src/strategy/strategy_runner.py` and `src/core/orchestrator.py`, not by the `core_engine` loop entry used by CLI.

3. **Trigger-without-intent invariant is not hard-fatal in core_engine path.**
   - It logs `[DECISION][ERROR] TRIGGER_WITHOUT_INTENT` and `[PIPELINE][ERROR] trigger_passed_but_no_intent` but does not raise.
   - In contrast, `RossMomentumStrategyV1.process_watchlist` does hard-fatal raise on `CRITICAL: TRIGGER_FIRED_NO_INTENT`.

4. **PAPER execution misconfig invariant in core_engine is present and scoped to execution requested.**
   - `execution_requested = execution_enabled_cfg or submission_enabled_cfg`
   - fatal if execution requested while disabled or readonly.

5. **Risk-approved decision reaches execution router path.**
   - `evaluate_trade_intents` emits risk outputs.
   - allowed decisions become `execution_candidates`.
   - passed to `execute_intents(mode, decisions)`.

6. **Current `execute_intents` does not submit real IBKR orders.**
   - It validates connectivity and registers callbacks.
   - For `SUBMITTED`, it synthesizes `broker_order_id = order_id_seed + index`.
   - It appends `ExecutionEvent` without placing orders through `IbkrLiveBroker` or `ExecutionEngine`.

## Readiness verdict
- **NOT READY** for proving true broker submission via this core_engine PAPER path.
- Reason: execution path currently simulates submission IDs instead of calling live/paper order placement adapters.

## Highest-priority patches before runtime certification
1. In `src/execution/order_router.py`, replace synthetic submission branch with real broker submit path (through canonical manager/client submit API or existing execution provider abstraction) and retain callback reconciliation.
2. In `src/core_engine/orchestrator.py`, promote `TRIGGER_WITHOUT_INTENT` from log-only to hard failure.
3. Ensure blocker reasons for config flags include explicit `IBKR_ORDER_SUBMISSION_ENABLED=false` and `READONLY=true` propagation in execution event detail for immediate operator diagnosis.

