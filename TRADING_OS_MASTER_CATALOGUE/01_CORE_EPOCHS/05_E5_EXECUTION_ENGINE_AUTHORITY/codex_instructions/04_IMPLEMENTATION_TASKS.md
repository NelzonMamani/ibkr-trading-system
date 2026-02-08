# Implementation Tasks — E5

Perform tasks ONLY if gaps are found:

1. Enforce single submission entry point
   - Ensure all order submissions route through ExecutionEngine
   - Block or assert against direct broker usage

2. Harden mode semantics
   - LIVE_READ_ONLY: deterministic reject with reason code
   - SIM: ensure simulated provider only
   - PAPER/LIVE: identical execution flow

3. Provider binding
   - Bind provider once at runtime start
   - Log provider and mode at boot

4. Order lifecycle normalization
   - Ensure canonical states are emitted
   - Normalize partial fills and terminal states

5. Traceability
   - Emit structured execution events
   - Include intent_id, order_id, broker_order_id, outcome

6. Safety & retry
   - Bound retries
   - Prevent duplicate submission on ambiguity

7. Tests
   - Add/extend tests to prove no bypass and mode parity
