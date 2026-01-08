PHASE_22_FIX_RUNTIME_MODE_AUTHORITY.md
# PHASE 22 — Fix Runtime Mode Authority (Critical)

## Observed Failure
Despite PHASE 22 being merged, the system still resolves:

- RUN_MODE = SIM
- SCANNER_MODE = TEACHING
- Market data source = SIM
- Broker = SIM_BROKER
- Phase banner = PHASE 4

This proves PHASE 22 is unreachable at runtime.

## Root Cause
RUN_MODE defaults to SIM and is never force-resolved.
SIM silently overrides LIVE_READ_ONLY even when IBKR settings are present.

## REQUIRED FIX (MANDATORY)

### 1. Make RUN_MODE authoritative
If any of the following are true:
- IBKR_MARKET_DATA_TYPE == LIVE
- IBKR_READONLY_ENABLED == True
- IBKR_PORT in {7496, 7497}

Then:
- RUN_MODE MUST resolve to LIVE_READ_ONLY
- SIM MUST NOT be allowed as a fallback

Fail fast if RUN_MODE is SIM under these conditions.

### 2. Enforce Live-Read-Only bootstrap
When RUN_MODE == LIVE_READ_ONLY:

- Phase banner MUST NOT reference PHASE 4
- Scanner MUST be LiveReadOnlyScanner
- MarketDataHub MUST use IBKR snapshot adapters
- ExecutionEngine MUST initialise in READ_ONLY mode
- SimBroker MUST NOT be instantiated

### 3. Add hard validation
Startup MUST raise if:
- RUN_MODE == SIM
- AND IBKR_MARKET_DATA_TYPE == LIVE
- AND IBKR_READONLY_ENABLED == True

This is an invalid configuration.

### 4. Logging (required)
Startup logs MUST clearly show:
- Effective RUN_MODE
- Scanner class name
- Market data source
- Broker adapter
- Execution policy

If any show SIM under LIVE_READ_ONLY conditions, raise.

## Constraints
- Do not change pattern logic
- Do not add execution capability
- Do not touch risk rules
- Do not add new phases

## Acceptance Criteria
A successful run MUST show:
- RUN_MODE = LIVE_READ_ONLY
- LiveReadOnlyScanner instantiated
- Market data source = IBKR
- Execution policy = READ_ONLY (no SIM broker)
- No PHASE 4 banner

END