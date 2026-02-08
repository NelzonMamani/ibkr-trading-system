# 03_DEFINITION_OF_TRADING_READY

## Formal definition (binary)
The Trading OS is **Trading Ready** iff all conditions below are true:

1. **Determinism in SIM**
   Given the same input stream and scenario seed, the system produces the same:
   - watchlist/focus outputs
   - intents
   - position lifecycle transitions
   - decision artifacts
   - event spine ordering

2. **Mode Parity**
   PAPER must mirror LIVE semantics for:
   - order lifecycle and rejections
   - timing/async boundaries
   - risk gates and kill-switch behavior
   Differences are allowed only where explicitly declared (e.g., capital caps, slippage model).

3. **No Placeholder Logic**
   Any stub, TODO, or empty function in critical paths is a hard FAIL.

4. **Safety Guarantees**
   - READ_ONLY emits zero broker orders.
   - LIVE can be configured to micro-risk (e.g., 1-share) and obey caps.
   - Kill-switch halts new orders and manages open positions according to doctrine.

5. **Recovery Guarantees**
   After a forced restart or disconnect, the system can:
   - reconcile positions/orders
   - resume the event spine without corruption
   - continue safely or halt safely depending on context

6. **Auditability**
   Every decision can be explained with:
   - inputs used (with provenance)
   - policy rule that allowed it
   - risk gate that approved it
   - execution outcome
   - resulting state transition

## What “ready” is NOT
- “It runs without crashing once.”
- “It prints logs.”
- “It compiles.”
- “It trades in a happy path but fails on disconnect.”
