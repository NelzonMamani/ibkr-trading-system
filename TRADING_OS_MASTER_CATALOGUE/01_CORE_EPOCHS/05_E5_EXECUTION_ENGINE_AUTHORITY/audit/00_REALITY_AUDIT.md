# E5 Reality Audit — Execution Engine Authority

Date: 2026-02-09

## Checklist Findings

1. **Single execution engine responsible for order submission?** YES.
   - `CoreOrchestrator` instantiates `ExecutionEngine` and routes risk decisions through it; order submission flows through `ExecutionProvider.place_order` from `ExecutionEngine._route_order`.

2. **Broker adapters unreachable directly by strategies/orchestrator in LIVE/PAPER?** YES (runtime path).
   - Orchestrator uses execution providers and execution engine; brokers are used for market data, not direct order submission.

3. **LIVE_READ_ONLY hard-block submission with explicit rejection?** YES.
   - `ExecutionEngine._preflight_check` returns `LIVE_READ_ONLY_BLOCK` and emits `ORDER_BLOCKED_READONLY` in READ_ONLY.
   - `IbkrExecutionProvider.place_order` also blocks when run_mode is READ_ONLY.

4. **PAPER and LIVE share the same execution code path?** YES.
   - `ExecutionEngine.execute_trade -> _route_order -> provider.place_order` is used for both; provider selection changes only by run mode.

5. **Partial fills normalized and reconciled correctly?** YES.
   - `SimBroker` and `IbkrLiveBroker` normalize `filled_quantity`, `remaining_quantity`, `fill_status`, and `average_fill_price` into `ExecutionResult`.

6. **Retry logic bounded and safe?** YES.
   - `ExecutionEngine._schedule_retry` enforces `EXECUTION_MAX_ATTEMPTS_BY_TRADER` and schedules retries only when explicitly requested.

7. **Execution attempts traceable (intent_id, order_id, outcome)?** YES.
   - `EventCollector` receives `ORDER_SUBMITTED`, gateway decisions, rejections, and explicit block reasons; `ExecutionResult` retains order identifiers.

8. **CLI/test path bypassing E5 in non-test modes?** NO bypass found in runtime flows; **Manual CLI exists**.
   - `src/cli/submit_one_order.py` provides a PAPER-only, explicitly gated manual submission tool. It enforces RUN_MODE=PAPER and IBKR guardrails; it is not used by orchestrator/strategies.

9. **Execution results persisted or emitted for storage?** YES.
   - `StorageEngine` persists `execution_output` in trade records; execution events are emitted via `EventCollector`.

## Summary
Execution authority is centralized in `ExecutionEngine` with mode-aware blocking, deterministic paper execution, and traceable outcomes. The only non-orchestrator submission path is a PAPER-only CLI with explicit safety gates.
