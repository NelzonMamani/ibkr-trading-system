FILE NAME
PHASE_15_STEP_15_1_LIVE_READ_ONLY_MARKET_DATA.md

TITLE
PHASE 15.1 — Live Read-Only Market Data (IBKR Connected, Zero Orders Guaranteed)

ROLE
You are continuing development of the IBKR Trading System.
You must preserve all guarantees established in Phases 13 and 14.
This phase introduces real IBKR market data under a strict read-only safety regime.

PHASE CONTEXT
Phase 14 completed full system hardening with zero logic changes.
Phase 15 transitions the system from simulated data to real broker data while guaranteeing that no orders can be placed.

OBJECTIVE (LOCAL)
Validate real-time IBKR market data ingestion, session handling, scanner realism, and Ross Momentum filtering
while making execution physically impossible.

GLOBAL SAFETY RULES (NON-NEGOTIABLE)
1. NO live or simulated broker orders may be placed.
2. Execution engine MUST be hard-gated or stubbed.
3. Any attempt to execute MUST result in an explicit READ_ONLY_BLOCK outcome.
4. The system must be safe to run unattended.
5. Safety guarantees override all other concerns.

CONFIGURATION REQUIREMENTS
The system MUST enforce:
- RUN_MODE = LIVE_READ_ONLY
- IBKR_READONLY_ENABLED = True
- Execution engine:
  - must not submit orders
  - must not simulate fills
  - must not retry
  - must raise or return a READ_ONLY_BLOCK result if invoked
- Logs MUST clearly state:
  - LIVE READ-ONLY MODE ACTIVE
  - NO EXECUTION ENABLED

SCOPE OF WORK
You SHALL:
- Connect to IBKR TWS / Gateway for market data only.
- Use real-time or delayed-frozen market data as configured.
- Validate:
  - symbol prices
  - bid/ask spread
  - volume
  - market session (PRE / REGULAR / AFTER / CLOSED)
- Run the scanner on the real universe.
- Allow pattern detection and strategy intent generation.
- Allow full risk evaluation for learning and validation.
- Explicitly block all execution attempts.

EXECUTION SAFETY CONTRACT
If a TradeIntent reaches Execution:
- The system MUST:
  - emit a READ_ONLY_BLOCK event
  - return an ExecutionResult with status=BLOCKED
  - include a clear rationale explaining read-only mode
- No broker routing.
- No retries.
- No ambiguity.

LOGGING & TEACHING REQUIREMENTS
Logs MUST explain:
- that the system is connected to live IBKR data
- that execution is disabled by design
- that this phase validates realism, not profitability

VALIDATION REQUIREMENTS
Run the system during:
- premarket
- regular market hours
- market closed

Confirm:
- real symbols appear in scanner output
- Ross Momentum filters behave realistically
- session detection is correct
- no IBKR warnings or violations occur
- no execution paths are reachable

ACCEPTANCE CRITERIA
This phase is complete when:
- The system runs stably on real IBKR data.
- Scanner output reflects live market conditions.
- Strategies and risk logic behave identically to SIM logic.
- Execution is provably impossible.
- Logs are explicit and unambiguous.

DELIVERABLE
- Live read-only system configuration
- Verified IBKR data ingestion
- Zero order placement capability

NEXT PHASE (LOCKED)
Upon successful completion, proceed to:
PHASE_16_STEP_16_1_LIVE_MICRO_EXECUTION_ONE_SHARE.md

END 