# PHASE_32_EXECUTION_ENGINE_IBKR.md
# PHASE 32 — EXECUTION ENGINE (IBKR) (AUTHORITATIVE)

## 0. Purpose
Implement the canonical execution pipeline that can:
- Translate approved intents into orders
- Submit orders to IBKR *only* when allowed by governance and run mode
- Simulate fills in SIM without broker routing
- Provide deterministic ExecutionResult artifacts

Epoch 3 must maintain strict safety:
- No order routing in LIVE_READ_ONLY (must be blocked)
- No routing when execution is disabled
- No routing without RiskEngine approval

## 1. Inputs and outputs
### 1.1 Inputs (required)
- Approved `RiskDecision` containing executable intents and sizing
- Current runtime config/run mode
- Broker adapter (SIM or IBKR)

### 1.2 Outputs (required)
- `ExecutionResult` (existing model) with:
  - order_id / broker_id (if applicable)
  - submitted: bool, filled: bool (SIM may fill deterministically)
  - avg_fill_price, filled_qty
  - rejection_reason (if blocked)
  - timestamps and idempotency keys

## 2. Canonical execution pipeline (stages)
ExecutionEngine must implement these stages in order:

### Stage A — Pre-flight gate
- Validate run mode allows execution (SIM / LIVE_MICRO / LIVE)
- Validate EXECUTION_ENABLED true
- Validate RiskDecision authorizes the intent
- Validate circuit breakers are not tripped
- If any fail: return ExecutionResult with `submitted=False` and explicit reason

### Stage B — Intent → InternalOrder translation
Translate TradeIntent into an internal canonical order model:
- symbol, side, qty, order_type, limit/stop parameters (when applicable)
- time-in-force policy
- risk tags propagated for audit

### Stage C — InternalOrder → BrokerOrder translation
- IBKR-specific order translation is isolated in adapter layer
- Ensure mapping is deterministic and tested

### Stage D — Submission and idempotency
- Enforce an idempotency key per intent per cycle (prevents duplicate orders)
- Submission must be retry-safe; retries must not create new orders unexpectedly
- If broker rejects: capture and persist the rejection reason

### Stage E — Fill handling (SIM vs live)
- SIM: deterministic fill model (configurable) and event emission
- LIVE: relies on broker callbacks; still must emit events and persist results

## 3. Required safety features
- LIVE_READ_ONLY must hard-block submission at multiple layers:
  - execution policy check
  - broker submission guard
  - IBKR adapter guard

- Any path that could place orders must require:
  - RiskDecision approval
  - Execution enabled
  - Allowed run mode
  - Circuit breakers not tripped

## 4. Required code touchpoints (expected)
- `src/execution/execution_engine.py`
- `src/adapters/brokers/ibkr/*` or existing `src/brokers/*` (consolidate logically, do not duplicate)
- `src/execution/order_gateway.py` for retries/idempotency
- `tests/test_ibkr_readonly.py`, `tests/test_liquidity_execution.py` (extend as needed)

## 5. Required tests (minimum)
1. LIVE_READ_ONLY blocks order routing (unit test + adapter guard test)
2. SIM produces ExecutionResult without broker submission
3. Duplicate intent IDs do not create duplicate submissions (idempotency test)
4. Rejection reasons propagate into ExecutionResult deterministically

## 6. Acceptance criteria
Phase 32 is complete when:
- ExecutionEngine can execute in SIM end-to-end (intent → result)
- ExecutionEngine is provably blocked in LIVE_READ_ONLY
- IBKR adapter submission is gated and safe-by-default
- Tests cover routing blocks, idempotency, and result correctness

---
End of PHASE_32_EXECUTION_ENGINE_IBKR.md
