FILE NAME
PHASE_15_COMPLETE_LIVE_VALIDATION.md

TITLE
PHASE 15 — Complete Live Market Validation (Zero-Risk, Read-Only, Pre-Execution Phase)

ROLE
You are continuing development of the IBKR Trading System.
You must preserve all guarantees established in Phases 13 and 14.
This phase validates real broker interaction while guaranteeing zero execution risk.

PHASE CONTEXT
Phase 14 delivered a hardened, warning-free SIM system with deterministic replay.
Phase 15 validates live market realism, broker connectivity behaviour, and safety controls
before any form of live execution is permitted.

GLOBAL NON-NEGOTIABLE SAFETY RULES
1. NO orders may be placed under any circumstances.
2. Execution engine MUST be physically incapable of submitting or simulating orders.
3. Any execution attempt MUST be blocked explicitly and logged.
4. The system MUST be safe to run unattended during market hours.
5. Safety overrides convenience, speed, and completeness.

PHASE OBJECTIVE (GLOBAL)
Prove that the system can connect to IBKR, consume real market data,
handle real-world imperfections, and fail safely,
without ever placing an order.

----------------------------------------------------------------
SUB-PHASE 15.1 — LIVE READ-ONLY MARKET DATA
----------------------------------------------------------------

OBJECTIVE
Validate live IBKR market data ingestion in strict read-only mode.

REQUIRED ACTIONS
- Enforce:
  - RUN_MODE = LIVE_READ_ONLY
  - IBKR_READONLY_ENABLED = True
- Connect to IBKR TWS / Gateway for data only.
- Validate:
  - prices
  - bid/ask spreads
  - volume
  - symbol universe
- Allow scanner, patterns, strategies, and risk to run on live data.
- Block execution deterministically with READ_ONLY_BLOCK results.

ACCEPTANCE
- Real symbols appear in scanner output.
- No order placement is possible.
- Logs clearly state LIVE READ-ONLY MODE ACTIVE.

----------------------------------------------------------------
SUB-PHASE 15.2 — LIVE DATA QUALITY & FALLBACK VALIDATION
----------------------------------------------------------------

OBJECTIVE
Ensure the system detects and handles degraded or missing live data.

REQUIRED ACTIONS
- Detect:
  - stale prices
  - missing bid/ask
  - zero volume anomalies
  - delayed vs real-time mismatches
- Flag data quality issues explicitly.
- Trigger fallback data sources if configured.
- Ensure scanner and risk respect data quality flags.

CONSTRAINTS
- No trading decisions may bypass data quality checks.
- No silent failures.

ACCEPTANCE
- Data issues are logged clearly.
- System continues safely with degraded inputs.
- No crashes or undefined behaviour.

----------------------------------------------------------------
SUB-PHASE 15.3 — LIVE SESSION & CALENDAR EDGE-CASE HANDLING
----------------------------------------------------------------

OBJECTIVE
Guarantee correct session classification in live conditions.

REQUIRED ACTIONS
- Validate detection of:
  - PRE
  - REGULAR
  - AFTER
  - CLOSED
- Handle:
  - holidays
  - half-days
  - early closes
- Ensure session state propagates correctly to all modules.

ACCEPTANCE
- Session detection matches real market conditions.
- No strategy or execution paths activate outside allowed sessions.
- Logs explain session transitions.

----------------------------------------------------------------
SUB-PHASE 15.4 — BROKER CONNECTIVITY & DEGRADATION HANDLING
----------------------------------------------------------------

OBJECTIVE
Ensure safe behaviour during IBKR connectivity issues.

REQUIRED ACTIONS
- Detect:
  - disconnects
  - partial connectivity
  - API warnings
  - reconnect events
- Throttle or pause system operation when data integrity is compromised.
- Resume safely after reconnect without state corruption.

CONSTRAINTS
- No execution paths may activate during degraded connectivity.
- No silent reconnects.

ACCEPTANCE
- Connectivity issues are logged explicitly.
- System remains stable and safe.
- No stale state leaks across reconnects.

----------------------------------------------------------------
SUB-PHASE 15.5 — LIVE-MODE KILL-SWITCH & EMERGENCY LOCKDOWN
----------------------------------------------------------------

OBJECTIVE
Guarantee immediate, irreversible safety shutdown if required.

REQUIRED ACTIONS
- Implement and validate:
  - manual kill-switch
  - automatic lockdown triggers
- Ensure kill-switch:
  - halts cycles
  - blocks execution
  - preserves audit logs
- Validate safe recovery after restart.

CONSTRAINTS
- Kill-switch overrides all other logic.
- No partial shutdown states allowed.

ACCEPTANCE
- Kill-switch works instantly and reliably.
- System shuts down cleanly.
- No orphaned state remains.

----------------------------------------------------------------
FINAL PHASE-LEVEL ACCEPTANCE CRITERIA
----------------------------------------------------------------

Phase 15 is COMPLETE when:
- Live IBKR data is consumed reliably.
- Data quality issues are detected and handled.
- Session classification is correct.
- Connectivity failures do not compromise safety.
- Emergency lockdown works as designed.
- Execution is provably impossible.
- Logs are explicit, complete, and explainable.

DELIVERABLE
- Live read-only validated system.
- Proven safety under real market conditions.
- Zero execution capability.

NEXT PHASE (LOCKED)
Upon successful completion, proceed to:
PHASE_16_COMPLETE_LIVE_MICRO_EXECUTION.md

END 