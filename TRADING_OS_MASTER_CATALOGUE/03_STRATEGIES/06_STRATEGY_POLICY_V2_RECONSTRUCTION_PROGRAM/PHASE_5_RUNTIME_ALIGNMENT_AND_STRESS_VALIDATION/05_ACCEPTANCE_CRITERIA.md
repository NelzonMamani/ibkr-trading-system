# PHASE 5 — Acceptance Criteria (Runtime Alignment & Stress Validation)

Phase 5 is complete only when all criteria below are satisfied.

## A. Policy governance (hard)

- Baseline snapshot exists at `AUDIT_EVIDENCE/strategy_policy_v2_baseline_snapshot.json`.
- Running `generate_audit_artifacts()` yields:
  - CERTIFIED: 20
  - FAIL: 0
  - INVALIDATED_PENDING_REVIEW: 0

## B. Runtime alignment (hard)

- All `strategy_policy_v2.py` modules import with no side effects.
- Orchestrator boot and one minimal cycle succeeds in:
  - SIM
  - PAPER
  - READ_ONLY
  - LIVE (execution disabled)
- Empty watchlists are accepted and treated as correct behavior.

## C. Stress validation (hard)

- At least 25 consecutive cycles complete without unhandled exceptions.
- Fault injection scenarios do not cause:
  - silent bypass of governance lock
  - corrupted DB state
  - orphaned asyncio tasks (where detectable)

## D. Evidence (hard)

All required evidence files exist under `AUDIT_EVIDENCE/phase_5/` and are committed.

## E. Documentation update (soft but expected)

- `SYSTEM_STATE_CERTIFIED.md` and the catalogue `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` include a Phase 5 completion note once complete.
