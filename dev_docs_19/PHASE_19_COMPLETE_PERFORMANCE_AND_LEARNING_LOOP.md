FILE NAME
PHASE_19_COMPLETE_PERFORMANCE_AND_LEARNING_LOOP.md

TITLE
PHASE 19 — Complete Performance Measurement & Learning Loop
(Accountability, Feedback, Improvement)

ROLE
You are continuing development of the IBKR Trading System.
You must preserve all guarantees established in Phases 13–18.
This phase introduces systematic performance measurement and learning,
without altering trading logic or behaviour.

PHASE CONTEXT
Phase 18 delivered disciplined exit and trade-management logic.
Phase 19 closes the loop by turning executed trades into structured feedback
for analysis, accountability, and future optimisation.

GLOBAL NON-NEGOTIABLE RULES
1. Performance tracking MUST NOT influence live decision-making in this phase.
2. No adaptive or self-modifying trading logic is permitted.
3. Measurement must be passive, observational, and auditable.
4. Metrics must be deterministic and replayable.
5. Learning outputs are informational only.

PHASE OBJECTIVE (GLOBAL)
Create a complete, explainable performance and learning framework that
captures what happened, why it happened, and how well rules were followed.

----------------------------------------------------------------
SUB-PHASE 19.1 — TRADE OUTCOME CLASSIFICATION
----------------------------------------------------------------

OBJECTIVE
Standardise how trade results are classified.

REQUIRED ACTIONS
- Classify every closed trade as:
  - WIN
  - LOSS
  - FLAT
- Capture:
  - realised PnL
  - R-multiple
  - duration held
  - exit reason
- Ensure classification is deterministic.

ACCEPTANCE
- Every trade has a clear outcome label.
- No ambiguous results.

----------------------------------------------------------------
SUB-PHASE 19.2 — STRATEGY-LEVEL PERFORMANCE METRICS
----------------------------------------------------------------

OBJECTIVE
Measure performance per strategy.

REQUIRED ACTIONS
- Track per-strategy:
  - total trades
  - win rate
  - average win
  - average loss
  - expectancy
  - profit factor
- Ensure metrics are computed from stored trade records only.

CONSTRAINTS
- No forward-looking bias.
- No smoothing or curve fitting.

ACCEPTANCE
- Metrics are reproducible and explainable.

----------------------------------------------------------------
SUB-PHASE 19.3 — PATTERN-LEVEL PERFORMANCE ANALYSIS
----------------------------------------------------------------

OBJECTIVE
Understand which Ross patterns perform best.

REQUIRED ACTIONS
- Track performance per pattern_name:
  - Gap and Go
  - ORB
  - First Pullback
  - VWAP Reclaim
  - HOD Break
- Capture:
  - frequency
  - win rate
  - average R
  - failure modes

ACCEPTANCE
- Pattern strengths and weaknesses are visible.

----------------------------------------------------------------
SUB-PHASE 19.4 — RISK & RULE ADHERENCE AUDIT
----------------------------------------------------------------

OBJECTIVE
Verify discipline and rule compliance.

REQUIRED ACTIONS
- Track:
  - stop adherence
  - exit discipline
  - max-loss respect
  - circuit-breaker triggers
- Flag:
  - rule violations
  - near-violations

CONSTRAINTS
- No automatic punishment or adaptation.
- Audit only.

ACCEPTANCE
- Discipline breaches are visible and logged.

----------------------------------------------------------------
SUB-PHASE 19.5 — TRADER-TYPE PERFORMANCE SEGMENTATION
----------------------------------------------------------------

OBJECTIVE
Separate performance by trader archetype.

REQUIRED ACTIONS
- Segment metrics by trader_type:
  - SCALPER
  - MOMENTUM
- Compare:
  - expectancy
  - volatility
  - hold times

ACCEPTANCE
- Trader-type strengths are clear.

----------------------------------------------------------------
SUB-PHASE 19.6 — SESSION & CONTEXTUAL PERFORMANCE
----------------------------------------------------------------

OBJECTIVE
Understand when performance occurs.

REQUIRED ACTIONS
- Track performance by:
  - market session (PRE / REGULAR / AFTER)
  - volatility regime
  - market direction (if available)

ACCEPTANCE
- Contextual edges are visible.

----------------------------------------------------------------
SUB-PHASE 19.7 — PERFORMANCE SNAPSHOTS & REPORTING
----------------------------------------------------------------

OBJECTIVE
Make performance review efficient and auditable.

REQUIRED ACTIONS
- Generate periodic snapshots:
  - daily
  - weekly
  - cumulative
- Ensure reports are:
  - human-readable
  - machine-parsable
  - replay-consistent

CONSTRAINTS
- No real-time optimisation.
- Reporting only.

ACCEPTANCE
- Reports match raw trade data exactly.

----------------------------------------------------------------
FINAL PHASE-LEVEL ACCEPTANCE CRITERIA
----------------------------------------------------------------

Phase 19 is COMPLETE when:
- Every trade outcome is classified.
- Strategy, pattern, and trader-type metrics are available.
- Rule adherence is auditable.
- Performance reports are reproducible.
- No feedback loops influence live trading.

DELIVERABLE
- Full performance measurement framework.
- Learning-ready dataset.
- Accountability and review tooling.

NEXT PHASE (LOCKED)
Upon successful completion, proceed to:
PHASE_20_COMPLETE_MULTI_STRATEGY_EXTENSION.md

END 