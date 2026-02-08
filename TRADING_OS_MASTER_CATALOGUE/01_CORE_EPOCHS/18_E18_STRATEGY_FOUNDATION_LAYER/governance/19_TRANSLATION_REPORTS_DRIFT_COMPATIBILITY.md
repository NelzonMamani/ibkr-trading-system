# E18 — STRATEGY POLICY TRANSLATION REPORTS, COVERAGE, DRIFT, COMPATIBILITY

E18 requires explicit artifacts every time a strategy is mapped or foundation changes.

MANDATORY ARTIFACTS:
1) STRATEGY_POLICY_TRANSLATION_REPORT.md
Must include:
- strategy_id
- policy_version hash
- foundation_version hash
- mapping_schema_version
- mapping table: policy requirements → foundation semantic contracts
- list of custom/strategy-local primitives (if any)
- enforced system invariants (E15/E16 safety only)
- compatibility verdict: PASS | PASS_WITH_EXCEPTIONS | FAIL
- drift status: policy_changed? foundation_changed? mapping_stale?

2) FOUNDATION_COVERAGE_CHECKLIST_<strategy_id>.md
- which SF_*, XL_*, C_*, K_*, candle primitives are used
- which are unused (informational)
- missing required primitives → FAIL

3) DRIFT_AND_COMPATIBILITY_REPORT_<strategy_id>.md
- differences since last mapping
- required re-mapping triggers

INVARIANTS:
- Mapping must be auditable and reproducible.
- The OS may suggest changes after N trades, but never auto-mutate policy.
- A strategy may opt-out of primitives; it may not opt-out of system safety layers.

END
