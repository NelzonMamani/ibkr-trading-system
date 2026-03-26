# P01 enforce real trigger firing — summary

## Exact missing conditions found
- Symbols could terminate without a normalized terminal stage classification across the live watchlist evaluation path; logs and traces were inconsistent across reject/fallback/intent branches.
- Strong-momentum fallback setup logic existed but was not phase-aware and used blunt thresholds, so valid PRE/RTH candidates could still die as `NO_SETUP`.
- Session gating in data-contract checks used mostly PRE-vs-RTH thresholds and did not emit an auditable per-phase threshold profile (volume/rvol/pct/spread).
- Runtime contract propagation to Ross runner did not carry `session_contract`, limiting phase/profile auditability.

## Exact code changes made
- Added explicit terminal-stage logging helper and enforced final terminal outcomes for all evaluated symbols (`CONTEXT_REJECTED`, `SETUP_REJECTED`, `CONFIRMATION_REJECTED`, `TRIGGER_REJECTED`, `INTENT_GENERATED`).
- Added phase-aware threshold model (`PRE`, `RTH_OPEN`, `RTH_MID`, `RTH_LATE`, `AH`) and applied it in data-contract gating and fallback trigger checks.
- Added robust strong-momentum force path with phase-aware trigger profile metadata/logging:
  - `[ROSS][SETUP][FORCED] ... phase=...`
  - `[ROSS][TRIGGER][FORCED] ... trigger_profile_id=...`
- Updated fallback momentum intent gate to respect per-phase thresholds and explicit AH restriction.
- Propagated `session_contract` from `StrategyRunner.process(...)` to `RossMomentumRunner.run(...)` and into strategy `process_watchlist(...)` signature.
- Added targeted runtime/contract tests:
  - `tests/test_session_contract_propagation_runtime.py`
  - `tests/test_pre_pct_gap_semantics_contract.py`
  - `tests/test_ross_terminal_stage_outcomes.py`

## Proof strong candidates now generate intent
- New tests verify strong candidates emit intents in PRE, RTH_OPEN, and RTH_MID phases.
- Terminal-stage tests verify every evaluated symbol emits `[ROSS][TERMINAL_STAGE] ...` with explicit outcome.
- `sample_stage_traces.json` includes a concrete trace where one symbol reaches `INTENT_GENERATED` and another safely rejects with `CONTEXT_REJECTED`.
- `pytest_targeted.txt` shows all targeted suites passing for this scope.
