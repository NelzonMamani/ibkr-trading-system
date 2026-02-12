
# 04_TEST_AND_VERIFICATION_PLAN — E22

## Unit tests (minimum)
- `test_e22_arbitration_deterministic_ordering`
- `test_e22_symbol_exclusivity_conflict`
- `test_e22_budget_breach_suppresses_strategy`

## Integration tests (minimum)
- Build a fixture where:
  - Strategy A and B both create ENTRY intent on same symbol
  - Arbitrator must allow exactly 1 and suppress the other deterministically
  - Evidence report includes both intents and reason code

## Verification script outputs
Verifier must write:
- compileall and pytest outputs
- verifier output JSON and summary MD
- EVIDENCE_INDEX and certification_verdict

## Non-regression
- Run `verification_scripts/system_integrity_and_capability_report.py --allow-overwrite`
and ensure it remains stable (excluding timestamps).
