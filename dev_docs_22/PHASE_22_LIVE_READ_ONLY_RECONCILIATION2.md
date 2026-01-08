PHASE_22_LIVE_READ_ONLY_RECONCILIATION2.md
# PHASE 22 — Live Read-Only Market Data (Reconciliation)

## Verified Baseline
SIM mode has been fully validated with:
- Deterministic execution
- Risk, cooldown, and registry enforcement
- Storage, replay, and graceful shutdown
No changes to SIM behaviour are permitted.

## Objective
Make `RUN_MODE=LIVE_READ_ONLY` a valid runtime configuration that:
- Uses live IBKR snapshot market data
- Never submits orders
- Never simulates fills
- Preserves all safety guarantees

## Confirmed Conflict
The following contradiction must be resolved:

- main.py and LiveReadOnlyScanner REQUIRE:
  - RUN_MODE=LIVE_READ_ONLY
  - IBKR_READONLY_ENABLED=True

- ExecutionEngine currently rejects:
  - any non-SIM run when IBKR_READONLY_ENABLED=True

This blocks PHASE 22 entirely.

## Required Resolution (minimal)
1. Allow ExecutionEngine to initialise in RUN_MODE=LIVE_READ_ONLY when IBKR_READONLY_ENABLED=True
2. Explicitly short-circuit all execution paths in this mode:
   - No gateway
   - No liquidity
   - No broker submission
3. Emit explicit logs:
   - Execution policy = READ_ONLY_DISABLED
   - Market data source = IBKR
   - Scanner type = LiveReadOnlyScanner

## Constraints
- SIM behaviour must not change
- PAPER and LIVE must remain blocked
- No refactors
- No new modes
- No execution capability introduced

## Validation
Startup must clearly log:
- Effective run mode
- Scanner selection
- Execution disabled by design
- IBKR snapshot data connectivity

END