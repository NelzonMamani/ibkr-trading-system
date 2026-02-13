# 07_ACCEPTANCE_CRITERIA.md
# E23 — Acceptance Criteria (Platform-Wide)
Last updated: 2026-02-13

E23 is accepted when a single E23 run produces ALL of:

1) platform_integrity_state.json generated with a non-empty platform_state.
2) SYSTEM_STATE_CERTIFIED.md regenerated and consistent with JSON.
3) DEPRECATION_LEDGER.md generated (even if empty, must exist).
4) RECONCILIATION_REPORT.md generated (must list drift checks performed).
5) Evidence written under an audit evidence location (E23's folder or global evidence folder).
6) Hard drift checks exist and fail the run if canonical invariants are violated (e.g., mode semantics drift).

Additionally:
- compileall passes
- pytest passes (or explicitly enumerated expected skips; default is full pass)
- SIM and PAPER and READ_ONLY boot cycles pass without unsafe routing
- READ_ONLY enforces non-routing in broker layer

END
