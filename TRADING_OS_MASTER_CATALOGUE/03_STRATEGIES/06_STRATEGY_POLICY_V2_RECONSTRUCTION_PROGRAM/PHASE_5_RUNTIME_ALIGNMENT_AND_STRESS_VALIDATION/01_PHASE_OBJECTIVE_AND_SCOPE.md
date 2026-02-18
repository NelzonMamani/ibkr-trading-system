# PHASE 5 — Objective and Scope (Runtime Alignment & Stress Validation)

## Objective

Prove that **Strategy Policy V2** is not only *certified on paper* but is **runtime-aligned**:

- The orchestration pipeline can **load, audit, and consume** policy for all strategies P01–P20.
- Policy-derived constraints are **enforceable** (even if some strategies are not yet fully implemented in trading logic).
- The platform handles **stress scenarios** (batch strategy cycles, missing data, broker unavailable, partial subscriptions) without corrupting state or silently bypassing governance.

## Scope

### In scope

1. **Policy Loading & Compilation**
   - Import all `src/strategies/*/strategy_policy_v2.py` modules.
   - Ensure no runtime import side effects, no hidden broker calls, no file-system writes on import.
   - Validate schema objects are stable and serialisable.

2. **Runtime/Orchestrator Alignment**
   - For each run mode (SIM/PAPER/READ_ONLY/LIVE with execution disabled):
     - Boot orchestrator.
     - Run at least one full cycle of “scan → watchlist → focus → intents → (execution gated)”.
   - Validate strategy selection / registration can operate with policy present.

3. **Policy Enforcement Hooks**
   - Confirm that runtime has explicit integration points for:
     - Execution constraints
     - Timeframe authority
     - Intrabar doctrine
     - Risk governance constraints (session limits, exposure limits) where applicable

4. **Governance Lock Enforcement**
   - Confirm baseline snapshot exists.
   - Confirm audit engine invalidates strategy if policy hash drifts.

5. **Stress & Fault Injection**
   - Run repeated orchestrator cycles.
   - Simulate broker unavailability.
   - Simulate market data gaps.
   - Simulate partial symbol universes (empty watchlists).
   - Ensure system remains traceable and fails safely.

### Out of scope (Phase 5)

- Writing full production trading logic for all strategies.
- LIVE execution enabling.
- Overhauling market data providers or broker adapter redesign.

## Deliverables

- Updated verification scripts (if required) that exercise runtime alignment.
- Evidence bundle under `AUDIT_EVIDENCE/phase_5/`.
- Any minimal patches needed to make runtime alignment true.
