PHASE_14_STEP_14_1_EVENT_SCHEMA_HARDENING.md 

PHASE 14.1 — Event Schema Hardening (SIM → Live Readiness, No Logic Changes) 

ROLE
You are continuing development of the IBKR Trading System exactly as specified in prior phases.
You must preserve all existing behaviour.
This phase is corrective and structural only.

PHASE CONTEXT
Phase 13 validated end-to-end orchestration, Ross Momentum risk overlay, deterministic SIM execution, and replay.
Phase 14 exists to remove ambiguity, warnings, and structural looseness before any live interaction.

OBJECTIVE (LOCAL)
Eliminate all event-schema ambiguities while preserving current system behaviour.

GLOBAL RULES
1. DO NOT modify strategy logic.
2. DO NOT modify risk logic.
3. DO NOT modify execution outcomes.
4. DO NOT change SIM determinism.
5. DO NOT introduce new features.
6. This phase is schema-only and structural.

SCOPE OF WORK
You MUST identify every event_type emitted during execution and replay and ensure it is formally registered.

Specifically, you SHALL:
- Register all missing event types observed in logs:
  - ORDER_SUBMITTED
  - ORDER_GATEWAY_DECISION
  - ORDER_REJECTED_HARD
  - ORDER_RETRY_SCHEDULED
- Align PERF_SNAPSHOT schema to include:
  - net_pnl
  - total_commissions
- Ensure no "[SCHEMA] Unknown event_type" warnings remain.
- Ensure no "[SCHEMA] event has extra keys" warnings remain.

EVENT SCHEMA REQUIREMENTS
For each event_type:
- Define a strict schema (expected keys and types).
- Allow optional keys only where justified.
- Preserve backward compatibility with existing emitted payloads.
- Do not drop or rename existing payload fields.

VALIDATION REQUIREMENTS
After implementation:
- Run the system in SIM mode for multiple cycles.
- Confirm:
  - Zero schema warnings.
  - Event replay functions identically.
  - Invariants remain OK.
  - Output behaviour is unchanged.

ACCEPTANCE CRITERIA
This phase is complete when:
- All emitted events are schema-registered.
- No schema warnings appear in logs.
- Replay reproduces identical results.
- No behavioural differences are observed.

DELIVERABLE
- Updated event schema registry.
- No new logic files.
- No behavioural diffs.
- Phase is self-contained and reversible.

NEXT PHASE (LOCKED)
Upon completion, proceed to:
PHASE_15_STEP_15_1_LIVE_READ_ONLY_MARKET_DATA.md

END 