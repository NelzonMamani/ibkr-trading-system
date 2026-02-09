# BLOCKER 01 — Scanner → Strategy watchlist selection drops all symbols

## What is broken
Ross Momentum watchlist selection drops every candidate in READONLY/TEACHING scenarios because the session label passed into the strategy selector is `RTH`, while the policy allowlist is configured for `REG` sessions. This mismatch causes the selector to treat all candidates as session-disallowed and returns an empty watchlist.

## Where it lives
- `src/strategies/ross_momentum/strategy_policy.py` in `select_watchlist` (session allowlist comparison).

## Contract violated
- **E6 Scanner → Strategy Contract**: strategy policy must honor scanner candidates and return a watchlist consistent with configured limits (watchlist_k=3 in the policy). The selector incorrectly filters all candidates due to session label normalization mismatch.

## Evidence / failing run
- Baseline pytest failure: `tests/test_scanner_policy_from_strategy.py::test_scanner_policy_limits_applied_in_teaching_mode`
- Output in `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/BASELINE/pytest.txt` shows `WATCHLIST_K_SELECTED (K=0)` and assertion failure expecting 3.
