FILE NAME
PHASE_17_COMPLETE_ROSS_MOMENTUM_PATTERN_REALISATION.md

TITLE
PHASE 17 — Complete Ross Momentum Pattern Realisation (From Teaching Placeholders to True Market Logic)

ROLE
You are continuing development of the IBKR Trading System.
You must preserve all guarantees established in Phases 13–16.
This phase replaces teaching-only pattern placeholders with real Ross Momentum logic.

PHASE CONTEXT
Phase 16 validated live micro-execution with strict capital protection.
Phase 17 implements true Ross Cameron momentum patterns incrementally,
ensuring every pattern is explicit, testable, explainable, and risk-aware.

GLOBAL NON-NEGOTIABLE RULES
1. No pattern may generate a TradeIntent without explicit, documented criteria.
2. Each pattern must be independently testable.
3. Pattern logic must be deterministic given identical inputs.
4. Pattern detection must not bypass risk or execution constraints.
5. Teaching placeholders must be fully removed or gated off.

PHASE OBJECTIVE (GLOBAL)
Implement the full Ross Momentum pattern suite using real market data,
with each pattern producing auditable, explainable TradeIntents.

----------------------------------------------------------------
SUB-PHASE 17.1 — GAP AND GO (REAL IMPLEMENTATION)
----------------------------------------------------------------

OBJECTIVE
Implement the canonical Ross “Gap and Go” pattern.

REQUIRED CRITERIA
- Premarket gap ≥ configured threshold (e.g., ≥ 8%)
- Relative volume ≥ configured threshold
- Float ≤ configured maximum
- Break of premarket high or early-session high
- Volume expansion at break

OUTPUT
- TradeIntent with:
  - pattern_name = GAP_AND_GO
  - confidence derived from signal confluence
  - explicit rationale listing all satisfied criteria

ACCEPTANCE
- Pattern triggers only when all criteria are met.
- False positives are explicitly filtered.

----------------------------------------------------------------
SUB-PHASE 17.2 — OPENING RANGE BREAKOUT (ORB)
----------------------------------------------------------------

OBJECTIVE
Implement Opening Range Breakout logic.

REQUIRED CRITERIA
- Defined opening range window
- Break and hold above opening range high
- Volume confirmation
- Alignment with market session rules

OUTPUT
- TradeIntent with pattern_name = ORB_BREAKOUT

ACCEPTANCE
- ORB logic respects time windows.
- No ORB signals outside defined opening range.

----------------------------------------------------------------
SUB-PHASE 17.3 — FIRST PULLBACK
----------------------------------------------------------------

OBJECTIVE
Implement First Pullback continuation pattern.

REQUIRED CRITERIA
- Prior valid momentum move
- Shallow pullback on decreasing volume
- Higher low formation
- Break of pullback high

OUTPUT
- TradeIntent with pattern_name = FIRST_PULLBACK

ACCEPTANCE
- Pattern invalidates on deep pullbacks.
- No pullback signals without prior momentum.

----------------------------------------------------------------
SUB-PHASE 17.4 — VWAP RECLAIM / HOLD
----------------------------------------------------------------

OBJECTIVE
Implement VWAP-based momentum confirmation.

REQUIRED CRITERIA
- Price reclaims VWAP after pullback
- Holds above VWAP for minimum duration
- Volume confirmation

OUTPUT
- TradeIntent with pattern_name = VWAP_RECLAIM

ACCEPTANCE
- VWAP logic is session-aware.
- No VWAP signals during illiquid periods.

----------------------------------------------------------------
SUB-PHASE 17.5 — HIGH OF DAY (HOD) CONTINUATION
----------------------------------------------------------------

OBJECTIVE
Implement High-of-Day breakout continuation.

REQUIRED CRITERIA
- Established intraday high
- Consolidation below HOD
- Break with volume expansion

OUTPUT
- TradeIntent with pattern_name = HOD_BREAK

ACCEPTANCE
- Prevents chasing extended moves.
- Requires consolidation before breakout.

----------------------------------------------------------------
SUB-PHASE 17.6 — FAILED BREAKOUT / TRAP FILTERS
----------------------------------------------------------------

OBJECTIVE
Prevent common Ross-style false breakouts.

REQUIRED FILTERS
- Immediate rejection after breakout
- Low volume break attempts
- Failed holds above key levels

OUTPUT
- Pattern suppression or explicit INVALIDATION_REASON

ACCEPTANCE
- False setups are blocked before execution.
- Invalidation reasons are logged.

----------------------------------------------------------------
SUB-PHASE 17.7 — PATTERN CONFIDENCE & SCORING MODEL
----------------------------------------------------------------

OBJECTIVE
Standardize confidence scoring across all Ross patterns.

REQUIRED ACTIONS
- Combine:
  - gap strength
  - volume confirmation
  - float alignment
  - market context
- Normalize confidence to a bounded scale.

OUTPUT
- confidence ∈ [0.0, 1.0]

ACCEPTANCE
- Confidence is comparable across patterns.
- Risk engine can use confidence consistently.

----------------------------------------------------------------
FINAL PHASE-LEVEL ACCEPTANCE CRITERIA
----------------------------------------------------------------

Phase 17 is COMPLETE when:
- All Ross Momentum patterns are fully implemented.
- Teaching placeholders are removed or disabled.
- Each TradeIntent includes explicit pattern_name, confidence, and rationale.
- Patterns are deterministic and replayable.
- Risk and execution layers remain unchanged.

DELIVERABLE
- Fully realized Ross Momentum pattern engine.
- Pattern-level auditability and explainability.
- Live-ready momentum detection.

NEXT PHASE (LOCKED)
Upon successful completion, proceed to:
PHASE_18_COMPLETE_EXIT_AND_TRADE_MANAGEMENT.md

END 