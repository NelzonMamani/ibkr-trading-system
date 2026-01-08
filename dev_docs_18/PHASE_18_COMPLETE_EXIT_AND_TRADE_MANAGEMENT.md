FILE NAME
PHASE_18_COMPLETE_EXIT_AND_TRADE_MANAGEMENT.md

TITLE
PHASE 18 — Complete Exit Logic & Trade Management (Discipline, Protection, and Consistency)

ROLE
You are continuing development of the IBKR Trading System.
You must preserve all guarantees established in Phases 13–17.
This phase implements disciplined, explicit, and auditable exit and trade-management logic.

PHASE CONTEXT
Phase 17 delivered full Ross Momentum pattern realisation and intent generation.
Phase 18 governs how trades are managed after entry, ensuring exits are intentional,
bounded, explainable, and never emotional or implicit.

GLOBAL NON-NEGOTIABLE RULES
1. Every open trade MUST have a defined exit plan.
2. No trade may remain open without an explicit exit condition.
3. Exits must be deterministic and replayable.
4. Exit logic must never loosen risk.
5. Hope-based holding is strictly forbidden.

PHASE OBJECTIVE (GLOBAL)
Implement robust, pattern-aware exit and trade-management logic that protects capital,
locks in gains methodically, and enforces discipline consistently.

----------------------------------------------------------------
SUB-PHASE 18.1 — INITIAL PROTECTIVE STOPS
----------------------------------------------------------------

OBJECTIVE
Ensure every trade is protected immediately after entry.

REQUIRED ACTIONS
- Define initial stop-loss placement per pattern:
  - Gap and Go: below VWAP / premarket low / defined risk level
  - ORB: below opening range low
  - First Pullback: below pullback low
  - HOD Break: below consolidation low
- Stops must be placed immediately upon fill where supported.

CONSTRAINTS
- Stops may not be widened automatically.
- Stop placement must be logged and auditable.

ACCEPTANCE
- No trade exists without a protective stop.
- Stop rationale is explicit.

----------------------------------------------------------------
SUB-PHASE 18.2 — TIME-BASED FAILSAFE EXITS
----------------------------------------------------------------

OBJECTIVE
Prevent stagnation and opportunity cost.

REQUIRED ACTIONS
- Define maximum hold time per trader_type and pattern.
- Trigger exit if:
  - expected momentum does not materialise
  - volume collapses
- Log exits as TIME_EXIT with rationale.

ACCEPTANCE
- Trades exit cleanly when momentum fails.
- No indefinite holding.

----------------------------------------------------------------
SUB-PHASE 18.3 — PROFIT TARGETS & PARTIALS (MICRO-SAFE)
----------------------------------------------------------------

OBJECTIVE
Lock in gains while preserving upside.

REQUIRED ACTIONS
- Define conservative profit targets (e.g., 1R, key levels).
- For micro-execution:
  - partials may be simulated or logged conceptually
  - full exit is acceptable in place of scaling
- Trailing logic must never reduce realised profit.

CONSTRAINTS
- No aggressive scaling.
- No martingale behaviour.

ACCEPTANCE
- Profit-taking is rule-based.
- Outcomes are explainable.

----------------------------------------------------------------
SUB-PHASE 18.4 — FAILURE & INVALIDATION EXITS
----------------------------------------------------------------

OBJECTIVE
Exit decisively when a setup fails.

REQUIRED ACTIONS
- Exit immediately on:
  - pattern invalidation
  - failed breakout
  - loss of key level (VWAP, HOD, OR low)
- Label exits explicitly (e.g., FAILED_SETUP_EXIT).

ACCEPTANCE
- Failed trades are exited quickly.
- Losses are small and controlled.

----------------------------------------------------------------
SUB-PHASE 18.5 — TRADE MANAGEMENT STATE MACHINE
----------------------------------------------------------------

OBJECTIVE
Formalise trade lifecycle states.

REQUIRED STATES
- OPENED
- PROTECTED
- IN_PROFIT
- EXIT_PENDING
- CLOSED

REQUIRED ACTIONS
- Enforce valid state transitions only.
- Prevent contradictory actions (e.g., trailing before protection).

ACCEPTANCE
- Trade lifecycle is explicit and auditable.
- Replay reconstructs identical state transitions.

----------------------------------------------------------------
SUB-PHASE 18.6 — EXIT EVENT LOGGING & AUDIT
----------------------------------------------------------------

OBJECTIVE
Ensure exits are fully traceable.

REQUIRED ACTIONS
- Emit explicit exit events:
  - EXIT_STOP_LOSS
  - EXIT_TIME
  - EXIT_TARGET
  - EXIT_FAILED_SETUP
- Capture:
  - exit price
  - exit reason
  - realised PnL
  - duration held

ACCEPTANCE
- Every exit has a reason.
- No silent closes.

----------------------------------------------------------------
FINAL PHASE-LEVEL ACCEPTANCE CRITERIA
----------------------------------------------------------------

Phase 18 is COMPLETE when:
- All trades have immediate protection.
- Exits are rule-based, not discretionary.
- Losses are bounded and explainable.
- Profits are taken methodically.
- Trade state transitions are explicit.
- Replay reproduces identical exit behaviour.

DELIVERABLE
- Fully implemented exit and trade-management logic.
- Discipline enforced at the system level.
- Audit-ready trade lifecycle.

NEXT PHASE (LOCKED)
Upon successful completion, proceed to:
PHASE_19_COMPLETE_PERFORMANCE_AND_LEARNING_LOOP.md

END 