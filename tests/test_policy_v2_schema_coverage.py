from verification_scripts.verify_all_strategy_policies_v2_schema import run_schema_coverage_verification


def test_policy_v2_schema_coverage_has_no_failures() -> None:
    outcome = run_schema_coverage_verification()
    assert not outcome["failures"], outcome["failures"]
