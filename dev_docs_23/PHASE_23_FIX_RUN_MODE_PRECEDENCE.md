PHASE_23_FIX_RUN_MODE_PRECEDENCE.md
# PHASE 23 — Fix RUN_MODE Precedence (Authoritative)

## Problem
System regressed to RUN_MODE=SIM despite live IBKR configuration.

This caused:
- Teaching scanner activation
- SIM market data
- Execution path being reached incorrectly
- Runtime safety abort

## Root Cause
RUN_MODE is still treated as a baseline default instead of a derived authority.
New flags (IBKR_API_WRITE_ALLOWED, EXECUTION_ENABLED) do not override SIM.

## REQUIRED FIX (MANDATORY)

### 1. RUN_MODE Must Be Derived, Not Defaulted
RUN_MODE must be recomputed AFTER config resolution.

If ALL are true:
- IBKR_MARKET_DATA_TYPE == LIVE
- IBKR_API_WRITE_ALLOWED == True
- EXECUTION_ENABLED == False

Then:
- RUN_MODE MUST be LIVE_READ_ONLY
- SIM MUST NOT be allowed
- Phase banner MUST NOT show PHASE 4

### 2. Hard Guard
If RUN_MODE == SIM AND IBKR_MARKET_DATA_TYPE == LIVE:
→ raise RuntimeConfigError and abort startup.

### 3. Scanner Selection Fix
When RUN_MODE == LIVE_READ_ONLY:
- Scanner MUST be LiveReadOnlyScanner
- Teaching Scanner MUST NOT be instantiated

### 4. Execution Reachability Fix
When EXECUTION_ENABLED == False:
- Orchestrator MUST NOT invoke execution stage at all
- ExecutionEngine MUST NOT receive risk decisions
- No RuntimeError should be raised — execution stage is skipped cleanly

### 5. Logging (Mandatory)
Startup logs MUST clearly show:
- Final RUN_MODE
- Phase banner
- Scanner class
- Market data source
- Execution stage skipped (explicit)

## Acceptance Criteria
A correct run MUST show:
- PHASE 23 banner
- RUN_MODE = LIVE_READ_ONLY
- LiveReadOnlyScanner instantiated
- Market data source = IBKR
- Execution stage skipped (not crashed)
- No RuntimeSafetyError

END