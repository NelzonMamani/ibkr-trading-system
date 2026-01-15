# PHASE_34_LIVE_TEST_MODE_AND_CIRCUIT_BREAKERS.md
# PHASE 34 — LIVE-TEST MODE & CIRCUIT BREAKERS (AUTHORITATIVE)

## 0. Purpose
Enable a safe, staged path from non-live testing to limited live execution, with circuit breakers that prevent catastrophic failures.

This phase formalizes:
- Live-test modes (SIM, LIVE_READ_ONLY, LIVE_MICRO, LIVE)
- Micro-live constraints
- Circuit breakers (latched) and reset policy
- Operational checks and runbook guidance

## 1. Staged rollout model (canonical)
### 1.1 Paper (external to system)
Manual trading only; system runs in data-only or SIM for validation.

### 1.2 SIM
- Execution simulated internally
- No broker routing
- Validates full pipeline end-to-end

### 1.3 LIVE_READ_ONLY
- Live market data
- Execution blocked at multiple layers
- Validates perception+decisions with real data, no orders

### 1.4 LIVE_MICRO
- Live execution allowed only under strict constraints:
  - max_qty_per_order = 1 share (default)
  - max_open_positions = 1 (default)
  - max_symbols_per_cycle small (default 5–10)
  - max_daily_loss very small (config; default conservative)
  - allowlist of symbols optional (recommended)
- Must require explicit enable flags

### 1.5 LIVE
- Live execution with full risk controls enabled
- Requires passing all safety self-tests and circuit breaker validation

## 2. Circuit breakers (latched)
Circuit breakers must be **latched** (once tripped, they remain active until reset action).

Minimum breaker set:
- Daily loss limit breach (net PnL <= -limit)
- Consecutive rejection threshold (broker rejects too many orders)
- Data quality degradation threshold (too many missing/incomplete market data flags)
- Unexpected exceptions threshold in execution loop

When tripped:
- Execution MUST be disabled immediately (hard stop)
- Exit engine must close or protect positions per policy
- Events must record breaker type, timestamp, and snapshot metrics

## 3. Reset policy (explicit)
Reset must be explicit and safe:
- Only allowed when no open positions OR when an emergency flatten has completed
- Only allowed by operator action (e.g., config flag on restart)
- Reset must be logged and persisted

## 4. Required code touchpoints (expected)
- `src/core/stop_controller.py` (extend for breaker states)
- `src/core/performance_registry.py` (daily limits and rule adherence)
- `src/execution/execution_engine.py` (honor breaker states)
- `src/execution/trade_exit_engine.py` (flatten on breaker)
- `tests/test_stop_controller.py` and add dedicated circuit breaker tests

## 5. Operational runbook (minimum embedded guidance)
The phase must document the operator checklist for LIVE_MICRO:
- Confirm run mode and flags
- Confirm execution enabled only if intended
- Confirm max_qty_per_order and max_open_positions are set
- Confirm daily loss limit is set
- Confirm symbol caps are set
- Confirm broker connection and read-only guard state
- Confirm logs show the safety banner (mode and routing status)

## 6. Acceptance criteria
Phase 34 is complete when:
- Circuit breakers exist, are latched, and are tested
- LIVE_MICRO constraints are enforced even if strategy emits larger sizing
- Reset logic is explicit and safe
- Logs and events clearly show breaker state and reasons
- End-to-end staged rollout is documented and reproducible

---
End of PHASE_34_LIVE_TEST_MODE_AND_CIRCUIT_BREAKERS.md
