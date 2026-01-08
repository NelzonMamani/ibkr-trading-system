PHASE_22_FIX_LIVE_READ_ONLY_ACTIVATION.md
# PHASE 22 — Fix Live Read-Only Activation (Blocking Bug)

## Problem Statement (Observed Runtime Evidence)
After merging PHASE 22, the system still boots with:
- Teaching Scanner
- SIM Market Data
- SIM Execution
- Phase 4 banner

This proves PHASE 22 is NOT being activated at runtime.

The system is silently falling back to SIM/TEACHING instead of enforcing LIVE_READ_ONLY.

## Root Cause
LIVE_READ_ONLY is not treated as a first-class runtime mode.
Control flow allows fallback to:
- Teaching Scanner
- SIM MarketDataHub
- SIM Broker

This invalidates PHASE 22 entirely.

## Required Fix (MANDATORY)

### 1. Enforce LIVE_READ_ONLY as a hard mode
If:
- RUN_MODE == LIVE_READ_ONLY

Then ALL of the following MUST occur:
- Scanner MUST be LiveReadOnlyScanner
- MarketDataHub MUST use IBKR snapshot data
- ExecutionEngine MUST initialise successfully
- Execution paths MUST be disabled explicitly (not via SIM fallback)

Any fallback to SIM or Teaching is a BUG.

### 2. ExecutionEngine reconciliation (precise)
ExecutionEngine MUST:
- Allow initialisation when:
  - RUN_MODE == LIVE_READ_ONLY
  - IBKR_READONLY_ENABLED == True
- Short-circuit all execution attempts with:
  - status=BLOCKED
  - reason=READ_ONLY_MODE
- Never route to SimBroker in LIVE_READ_ONLY

### 3. Scanner selection enforcement
CoreOrchestrator MUST:
- Ignore SCANNER_MODE when RUN_MODE == LIVE_READ_ONLY
- Always instantiate LiveReadOnlyScanner
- Fail fast if IBKR_READONLY_ENABLED is False

### 4. Market data source enforcement
MarketDataHub MUST:
- Use IBKR market data adapters in LIVE_READ_ONLY
- Emit a startup log:
  "[VALIDATION] Market data source: IBKR (READ_ONLY)"

### 5. Logging & validation (non-negotiable)
Startup MUST clearly log:
- Effective RunMode
- Scanner class in use
- Market data source
- Execution policy = DISABLED (READ_ONLY)

If any of these are not true, startup MUST raise.

## Constraints
- SIM behaviour must remain unchanged
- PAPER and LIVE must remain blocked
- No refactors
- No new modes
- No execution capability added

## Acceptance Criteria
A successful run MUST show:
- LiveReadOnlyScanner instantiated
- IBKR snapshot market data logs
- ExecutionEngine initialised with execution disabled
- No teaching scanner
- No SIM market data
- No broker routing

END