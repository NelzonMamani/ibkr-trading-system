# E18 — TRANSLATION REPORTS, COVERAGE, DRIFT, COMPATIBILITY TASKS

Source of truth: governance/19_TRANSLATION_REPORTS_DRIFT_COMPATIBILITY.md

Task:
Implement mandatory artifact generation for each strategy mapping.

Artifacts (per strategy_id):
1) STRATEGY_POLICY_TRANSLATION_REPORT.md
Must include:
- strategy_id
- policy_version hash (or version string)
- foundation_version hash
- mapping_schema_version
- mapping table: policy requirements → foundation semantic contracts
- list of custom primitives (if any)
- enforced system invariants (E15/E16 safety only)
- compatibility verdict: PASS | PASS_WITH_EXCEPTIONS | FAIL
- drift: policy_changed? foundation_changed? mapping_stale?

2) FOUNDATION_COVERAGE_CHECKLIST_<strategy_id>.md
- list all SF/XL/C/K/candle primitives and mark:
  - used / unused / custom
- any missing REQUIRED items for that strategy => FAIL

3) DRIFT_AND_COMPATIBILITY_REPORT_<strategy_id>.md
- changes since last mapping
- triggers for re-mapping

Rules:
- Reports must be reproducible and deterministic.
- No policy auto-mutation. Suggestions are advisory and versioned elsewhere.

Deliverables:
- Report generator module
- Command/entrypoint to generate reports for all strategies
- Unit tests verifying report structure determinism

END
