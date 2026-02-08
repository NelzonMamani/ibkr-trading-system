# 11_REQUIRED_ARTIFACTS_AND_REPORTS

## E21 must output these artifacts (minimum)
1. E21_CERTIFICATION_REPORT.md
   - PASS/FAIL + timestamp + git SHA + environment summary
2. E21_MODE_PARITY_MATRIX.md
3. E21_SCENARIO_COVERAGE.md
4. E21_FAILURE_DRILLS_REPORT.md
5. E21_NON_INTERFERENCE_PROOF.md
6. E21_E2E_RUN_LOGS/
   - structured logs
   - event spine export (if supported)
7. E21_EVIDENCE_INDEX.json
   - machine-readable pointers to all evidence files

## Evidence retention
Retention rules must reference M6 (data lifecycle). Evidence must be deletable by housekeeping tooling (E12) without corrupting the DB or core history.
