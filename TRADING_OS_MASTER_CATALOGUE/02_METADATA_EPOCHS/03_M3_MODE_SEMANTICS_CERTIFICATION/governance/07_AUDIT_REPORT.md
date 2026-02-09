# AUDIT REPORT

M3_MODE_SEMANTICS_CERTIFICATION is certified when:

- All modes behave as declared in governance.
- No undocumented mode behavior exists.
- Safety invariants hold across configuration, orchestrator, execution, and broker layers.
- Verification tooling and pytest coverage pass without violations.

## Conflict resolution

- Any code path that violates declared mode semantics forces NOT CERTIFIED.
- Ambiguity or undocumented behavior must be treated as a violation.
- Certification status cannot be upgraded until violations are resolved and
  re-verified with updated audit evidence.

END
