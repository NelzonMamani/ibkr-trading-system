# Test Enforcement Requirements (pytest)

## Principle
The audit engine is not sufficient alone. Institutional governance requires **tests that fail CI** if the policies regress.

## Required Tests
Create or extend tests under `tests/metadata/`:

1) `test_strategy_policy_v2_presence.py`
- verifies all 20 strategies have a `strategy_policy_v2.py` with `POLICY_V2`

2) `test_strategy_policy_v2_institutional_matrix_v2.py`
- executes audit engine and asserts:
  - report files are generated (or generation is invoked)
  - matrix v2 file exists and includes all P01..P20 rows
  - verdict computation rules hold

3) `test_strategy_policy_v2_minimum_section_thresholds.py`
- for each strategy:
  - enforce global minimums
  - enforce intraday minimums unless N/A declared
  - fail on default-only

4) `test_strategy_policy_v2_non_regression_p01.py`
- P01 must remain CERTIFIED

## Test Determinism
- No network calls
- No market-data dependency
- Do not instantiate live brokers
- Tests must run under Windows and Linux

## CI Integration
These tests become required gates for:
- strategy certification PRs
- future strategy modifications
