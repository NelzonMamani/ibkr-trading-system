# Execution Authority Callback Audit (2026-03-31)

## Gaps closed
- Added canonical callback-first execution authority with validated state transitions.
- Added idempotent fill processing + position lifecycle transitions.
- Added persistence tables for execution orders/fills/position lifecycle.
- Removed synthetic `broker_order_id` generation from `execute_intents` authority path (LIVE/PAPER).

## Files changed
- `src/execution/execution_authority.py`
- `src/execution/order_router.py`
- `src/adapters/brokers/ibkr/ibkr_client.py`
- `src/core_engine/events.py`
- `src/storage/sqlite_store.py`
- `src/storage/storage_engine.py`
- `tests/test_execution_authority.py`

## State machine semantics
- States: CREATED, SUBMITTING, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCEL_PENDING, CANCELLED, REJECTED, INACTIVE, EXPIRED, ERROR.
- Monotonic ranking enforcement with terminal-state protection.
- Lifecycle source tagged as local_submit / ibkr_order_status_callback / ibkr_execution_callback / reconciliation.

## Callback surfaces wired
- `openOrder`
- `orderStatus`
- `execDetails`
- `commissionReport` (existing preserved)
- `position`
- `positionEnd`

## Dedup approach
- Primary: `exec_id` uniqueness.
- Secondary: `(broker_order_id, cumulative_qty)` snapshot dedupe.

## Persistence fields
- Orders: local_submission_id, broker_order_id, order_ref, intent_id, strategy_name, symbol, side, requested_qty, lifecycle_state, raw_broker_status, lifecycle_source, perm_id, timestamps.
- Fills: broker_order_id, exec_id, perm_id, symbol, side, fill_qty, cumulative_qty, fill_price, avg_fill_price, timestamp, source.
- Position lifecycle: symbol, strategy_name, action, quantity_after, avg_entry_after, realized_pnl_delta, causal_exec_id, timestamp, source.

## Tests run
- `pytest -q tests/test_execution_authority.py tests/test_actionability_micro_execution_contract.py tests/test_pr549_execution_pipeline_enforcement.py`
- `pytest -q tests/test_storage_schema_epoch4.py`

## Runtime verification commands
- `python verification_scripts/verify_paper_trade_lifecycle.py`
- `python verification_scripts/verify_execution_pipeline_live.py`
- `python verification_scripts/verify_paper_execution_harness.py`

## Remaining limitations
- Runtime callback activation depends on active IBKR session and callback delivery from TWS/Gateway.
- Reconciliation remains enabled as secondary state repair path.
