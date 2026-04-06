# PREFLIGHT CERTIFICATION — ROSS PIPELINE (UPDATED 2026-04-06)

## 1) Runtime path in use

The active CLI PAPER flow is:

`src.main -> src/core_engine/orchestrator.py -> src/execution/order_router.py -> IBKR connection manager/client callbacks`

This is the path generating current `[ROSS]`, `[PIPELINE]`, `[EXECUTION]`, and `[LIFECYCLE]` logs and is the path assessed below.

## 2) Structural codepath findings

### 2.1 Submission branch in `src/execution/order_router.py`
- `execute_intents(...)` validates IBKR connectivity for PAPER/LIVE and registers IBKR execution callbacks.
- For `ALLOW` decisions it emits `action="SUBMITTED"` with non-null `broker_order_id` and records order lifecycle state.
- The current branch **does not call `placeOrder` directly in `order_router.py`**; instead it relies on IBKR-connected runtime plumbing and callback-driven order-state reconciliation in this path.

### 2.2 Synthetic order-id behavior (current reality)
- Order IDs are derived from `connected_client_id * 1_000_000 + index` when IBKR metadata is available.
- If not in PAPER/LIVE or explicit test mode, fallback ids are local index-based.
- Therefore, synthetic/fallback IDs are now constrained to non-broker execution contexts (SIM/READ_ONLY/TEST/degraded metadata), not the intended normal PAPER/LIVE connected path.

### 2.3 Fill authority and reconciliation hardening (continued)
- Fill authority is now locked to `execDetails` callbacks; `orderStatus`-reported fills are explicitly logged and ignored as fill authority.
- Duplicate fills are de-duplicated via `(order_id, exec_id)` and counted.
- Order↔fill linkage is validated (`order_id` symbol vs callback symbol); mismatches are rejected and counted.
- Position state remains fill-driven and broker positions are passively reconciled without synthetic fill creation.
- Callback diagnostics now include both delay warning and stuck-order escalation.
- Execution summary now includes duplicate-fill, linkage-mismatch, callback-delay, and stuck-order counters.

### 2.4 `trigger_without_intent` status on current core_engine path
- On the active `src/core_engine/orchestrator.py` path, `TRIGGER_WITHOUT_INTENT` is emitted as explicit error/blocker logging and terminal classification.
- It is **not a hard-fatal exception path** in current cycle flow (it blocks symbol progression rather than crashing the run).

## 3) Runtime evidence already observed

Runtime evidence from recent PAPER + IBKR submission work (the evidence that drove this correction request) indicates the system now demonstrates:
- setup detection
- trigger firing
- intent creation
- risk pass on some symbols
- execution handoff
- IBKR dispatch behavior
- non-null `broker_order_id` capture
- `ORDER_SUBMITTED` / `ORDER_ACKNOWLEDGED` lifecycle states

This runtime evidence is consistent with the currently inspected structural path and no longer supports a blanket “cannot submit” conclusion.

## 4) Proven working

- End-to-end symbol progression can reach execution lifecycle states beyond risk gate.
- Broker-order identifiers are emitted and tracked in lifecycle state.
- Callback-driven execution lifecycle, fill dedupe, and reconciliation diagnostics are implemented on the active execution path.

## 5) Not yet proven

- Deterministic proof that **all** fills are observed through `execDetails` under all broker/network timing conditions.
- Session-level proof of stable order↔fill linkage under high callback concurrency.
- Full closed-loop production evidence that fill-driven local position plus broker position reconciliation remains drift-free across multi-order/multi-symbol runs.

## 6) Remaining risks

- Broker callback timing asymmetry can still produce transient unmatched callbacks.
- Passive reconciliation is corrective but does not replace robust historical replay for missed callback windows.
- PAPER evidence does not automatically satisfy LIVE operational risk, session liquidity, or operational controls.

## 7) Updated readiness verdict

**Updated verdict:**
- The current system is structurally and runtime-consistent with broker submission validation in PAPER.
- It is **not yet ready for unrestricted LIVE scaling** until fill authority, fill linkage robustness, and reconciliation behavior are validated over broader runtime scenarios.

## 8) Highest-priority next patches

1. Persist `exec_id` dedupe state and linkage diagnostics into durable storage for post-mortem auditability.
2. Add reconciliation replay window (recent executions + positions) at startup to reduce missed-callback risk after restart.
3. Add alert thresholds/escalation policy for repeated unmatched callbacks and stuck-order events.
4. Add integration tests that model out-of-order `orderStatus`/`execDetails` and partial-fill sequences at scale.
