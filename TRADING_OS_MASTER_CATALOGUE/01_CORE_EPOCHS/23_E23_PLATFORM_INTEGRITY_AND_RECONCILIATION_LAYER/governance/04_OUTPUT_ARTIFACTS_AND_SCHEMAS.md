# 04_OUTPUT_ARTIFACTS_AND_SCHEMAS.md
# E23 — Output Artifacts & Schemas (Authoritative)
Last updated: 2026-02-13

E23 generates (or regenerates) the following artifacts from evidence and reconciliation decisions.

## A) platform_integrity_state.json (machine-readable)
Purpose: single authoritative platform verdict and reconciliation summary.

Required fields:
- timestamp_utc
- git_commit (if available)
- run_context (local/CI; python version; OS)
- canonical_run_modes
- core_epochs: dict[str, status]
- metadata_epochs: dict[str, status]
- strategies: dict[str, status]
- drift_items: list[...]
- deprecation_ledger: list[...]
- platform_state: one of
  - TRADING_READY_SIM
  - TRADING_READY_PAPER
  - TRADING_READY_READ_ONLY
  - TRADING_READY_LIVE
  - NOT_READY
  - DRIFT_DETECTED
  - INVARIANT_VIOLATION

## B) SYSTEM_STATE_CERTIFIED.md (human-readable, regenerated)
Purpose: single human truth surface matching JSON verdicts.

Must include:
- canonical modes + alias normalization
- epoch statuses derived from evidence
- strategy statuses
- verification notes + how to reproduce

## C) DEPRECATION_LEDGER.md (human-readable)
Purpose: explicit global reconciliation decisions.
Must include:
- what is deprecated/superseded/ignore/compat-only
- reason
- pointer to governing truth + evidence

## D) RECONCILIATION_REPORT.md (human-readable)
Purpose: drift summary + fix actions taken + fix actions recommended.

## E) AUDIT_EVIDENCE append
All E23 runs must write evidence artifacts:
- JSON summary output
- verification command list executed
- drift list

END
