PHASE_22_Live_Read-Only_Market_Data_Reconciliation_&_Hardening.md
# PHASE 22 — Live Read-Only Market Data (Reconciliation & Hardening)

## Objective
Reconcile configuration and execution guards so that `RUN_MODE=LIVE_READ_ONLY` is a valid, non-contradictory runtime state.

This phase MUST:
- Allow live IBKR market data
- Forbid *all* order submission
- Preserve all existing SIM and safety guarantees
- Introduce no new execution paths

This phase MUST NOT:
- Enable LIVE trading
- Change strategy logic
- Change risk logic
- Change storage schemas

## Required Analysis (before any code changes)
1. Identify all places where `RUN_MODE=LIVE_READ_ONLY` is checked.
2. Identify all places where `IBKR_READONLY_ENABLED=True` blocks execution.
3. Document the exact contradiction between:
   - ExecutionEngine non-SIM read-only restriction
   - main / LiveReadOnlyScanner expectations

## Required Resolution
Implement the **minimal change** necessary so that:

- `RUN_MODE=LIVE_READ_ONLY`
- `IBKR_READONLY_ENABLED=True`

is a valid configuration that:
- Instantiates `LiveReadOnlyScanner`
- Connects to IBKR for snapshot market data
- Skips or short-circuits execution cleanly
- Emits explicit log lines confirming:
  - live data enabled
  - execution disabled by design

## Validation Requirements
Add runtime validation logs that clearly state:
- Effective run mode
- Scanner type selected
- Execution policy (disabled / simulated / allowed)
- Broker adapter in use

## Safety Constraints
- SIM behaviour must remain unchanged
- PAPER and LIVE must remain blocked
- No code path may submit orders to IBKR

## Deliverable
- Code changes only where strictly required
- No refactors
- No new modes
- No behavioural changes outside LIVE_READ_ONLY reconciliation

END