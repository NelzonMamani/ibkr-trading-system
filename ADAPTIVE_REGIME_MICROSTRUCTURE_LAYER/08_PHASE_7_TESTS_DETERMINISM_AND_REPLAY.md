# Phase 7 — Tests: Determinism & Replay Safety
Last updated: 2026-01-19

## Objective
Prove determinism and ensure the layer does not break replay invariants.

## Deliverables
1) tests/test_regime_determinism.py
- Run a small in-memory cycle twice with the same synthetic inputs
- Assert regime snapshot equality (deep compare)
- Assert policy decision equality

2) tests/test_regime_live_readonly_missingness.py
- Provide inputs mimicking IBKR delayed snapshot at closed market (bid=-1, ask=-1, last=None)
- Assert snapshot label is AFTER_HOURS_THIN or UNKNOWN deterministically depending on session config.

3) Replay integration
- Ensure regime events are included in replay outputs in SIM mode.
- Ensure live modes still lock down replay as designed.

## Acceptance criteria
- pytest -q passes.
- No flaky tests.
