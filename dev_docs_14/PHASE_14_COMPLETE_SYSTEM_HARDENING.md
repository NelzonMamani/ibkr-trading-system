FILE NAME
PHASE_14_COMPLETE_SYSTEM_HARDENING.md

TITLE
PHASE 14 — Complete System Hardening (SIM → Live Readiness, Zero Logic Change)

ROLE
You are continuing development of the IBKR Trading System.
You must preserve all existing behaviour validated in Phase 13.
This phase is corrective, structural, and safety-focused only.

PHASE CONTEXT
Phase 13 validated end-to-end orchestration, Ross Momentum risk overlay, deterministic SIM execution, replay, and invariants.
Phase 14 removes all remaining ambiguity, warnings, and structural looseness before any live market interaction.

GLOBAL NON-NEGOTIABLE RULES
1. DO NOT modify strategy logic.
2. DO NOT modify pattern logic.
3. DO NOT modify risk decision logic.
4. DO NOT change execution outcomes.
5. DO NOT alter SIM determinism.
6. DO NOT introduce new features.
7. DO NOT expand scope beyond hardening.
8. All behaviour before and after this phase must be functionally identical.

PHASE OBJECTIVE (GLOBAL)
Achieve a warning-free, schema-consistent, auditable, and shutdown-safe system suitable to progress into live read-only mode.

----------------------------------------------------------------
SUB-PHASE 14.1 — EVENT SCHEMA HARDENING
----------------------------------------------------------------

OBJECTIVE
Eliminate all event-schema ambiguity.

REQUIRED ACTIONS
- Register all emitted event types in the schema registry, including but not limited to:
  - ORDER_SUBMITTED
  - ORDER_GATEWAY_DECISION
  - ORDER_REJECTED_HARD
  - ORDER_RETRY_SCHEDULED
  - READ_ONLY_BLOCK (if applicable later)
- Align PERF_SNAPSHOT schema to explicitly include:
  - net_pnl
  - total_commissions
- Ensure no "[SCHEMA] Unknown event_type" warnings remain.
- Ensure no "[SCHEMA] event has extra keys" warnings remain.

CONSTRAINTS
- Preserve existing payload fields exactly.
- Do not rename or remove fields.
- Optional fields must be explicitly documented.

ACCEPTANCE
- Zero schema warnings across multiple SIM cycles.
- Event replay reproduces identical results.

----------------------------------------------------------------
SUB-PHASE 14.2 — STORAGE CONTRACT HARDENING
----------------------------------------------------------------

OBJECTIVE
Ensure storage contracts are explicit, stable, and audit-ready.

REQUIRED ACTIONS
- Formalize TradeRecord schema:
  - scanner_output
  - pattern_output
  - strategy_output
  - risk_output
  - execution_output
  - trade_outcomes
  - performance_snapshot
- Validate that all stored objects are serializable and deterministic.
- Ensure placeholder storage acknowledges full schema correctly.

CONSTRAINTS
- No persistence backend changes.
- No database schema migrations.
- Teaching-only placeholder storage remains acceptable.

ACCEPTANCE
- Storage stage emits no warnings.
- TradeRecord structure is complete and consistent across cycles.

----------------------------------------------------------------
SUB-PHASE 14.3 — RISK DECISION PERSISTENCE & AUDIT HARDENING
----------------------------------------------------------------

OBJECTIVE
Guarantee that every risk decision is fully auditable and replay-safe.

REQUIRED ACTIONS
- Ensure RiskDecision includes:
  - explicit reason_code when blocked
  - clear rationale text
  - trader_type and strategy_name
- Validate that all RiskDecision objects are stored in TradeRecord.
- Confirm replay reconstructs identical risk outcomes.

CONSTRAINTS
- No new risk rules.
- No changes to allow/block logic.

ACCEPTANCE
- Risk decisions are traceable end-to-end.
- Replay shows identical risk gating.

----------------------------------------------------------------
SUB-PHASE 14.4 — EXECUTION RETRY & EXHAUSTION HARDENING
----------------------------------------------------------------

OBJECTIVE
Prevent unbounded retries and ensure deterministic exhaustion.

REQUIRED ACTIONS
- Enforce a maximum retry count per order.
- Ensure retry exhaustion results in a terminal ExecutionResult with clear rationale.
- Ensure retries are deterministic and replayable.

CONSTRAINTS
- Do not change gateway decision mapping.
- Do not change fill logic.
- Retry limits must be conservative and explicit.

ACCEPTANCE
- No infinite retry loops.
- Execution results are terminal and explainable.

----------------------------------------------------------------
SUB-PHASE 14.5 — SHUTDOWN & ORPHAN SAFETY VALIDATION
----------------------------------------------------------------

OBJECTIVE
Guarantee safe shutdown with zero orphaned trades or orders.

REQUIRED ACTIONS
- Validate that shutdown:
  - force-closes all active trades
  - unregisters all registry entries
  - emits explicit shutdown events
- Ensure shutdown behaviour is deterministic and replay-safe.

CONSTRAINTS
- No behavioural change to shutdown logic.
- Only validation and explicit guarantees.

ACCEPTANCE
- Registry verification passes after shutdown.
- No active trades remain.
- Shutdown logs are explicit and complete.

----------------------------------------------------------------
FINAL PHASE-LEVEL ACCEPTANCE CRITERIA
----------------------------------------------------------------

Phase 14 is COMPLETE when:
- Zero schema warnings appear.
- Zero storage warnings appear.
- Risk decisions are fully auditable.
- Execution retries are bounded and deterministic.
- Shutdown leaves the system in a clean state.
- Replay reproduces identical behaviour.
- No logic changes are detected.

DELIVERABLE
- Hardened schemas.
- Explicit contracts.
- Warning-free SIM execution.
- No feature or logic diffs.

NEXT PHASE (LOCKED)
Upon successful completion, proceed to:
PHASE_15_STEP_15_1_LIVE_READ_ONLY_MARKET_DATA.md

END 