# E5 — Core Invariants (Hard Laws)

1. **No execution without approval**
   - Every non-exit intent must have an APPROVE decision from Risk Engine (E3).
   - Exit intents may be permitted under special safety rules (e.g., emergency flatten), but must still be logged.

2. **Mode semantics are enforced at execution boundary**
   - LIVE_READ_ONLY: submission is forbidden; must produce deterministic rejection.
   - SIM: must not call broker; uses simulated provider.
   - PAPER: must use paper provider; semantics mirror LIVE as closely as possible.
   - LIVE: uses live provider with all guards.

3. **PAPER mirrors LIVE**
   - Risk constraints identical (locked earlier).
   - Execution code path equivalent except provider endpoint.
   - Same order lifecycle, same reconciliation logic.

4. **Lifecycle consistency**
   - Execution cannot move a position to an invalid state.
   - Partial fills must not create negative or impossible positions.
   - Terminal states are immutable without explicit correction events.

5. **No silent failure**
   - Failures must carry reason codes (transient/permanent/guard violation).
   - Retries must be bounded and safe.

6. **Traceability**
   - Every attempt emits a trace event containing: run_mode, symbol, intent_id, order_id, broker_order_id (if any),
     and a terminal outcome reason.
