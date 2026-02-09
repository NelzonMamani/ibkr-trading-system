# BLOCKER_01

## Summary
Scanner → strategy contract enforcement had two gaps: scanner requests were not validated before execution, and watchlist selection compared session labels without normalizing the policy allowlist ("REG" vs "RTH"), causing valid candidates to be dropped. This broke scanner contract guarantees for strategy readiness.

## Impact
- **Epochs impacted**: E6 (Scanner → Strategy Contract), E16 (No-Trade Contexts / gating safety)
- **Contracts impacted**: Scanner request contract (strategy → scanner), watchlist selection/session-phase alignment

## Location
- `src/scanner/scanner_contract.py`
- `src/scanner/scanner_runner.py`
- `src/strategies/ross_momentum/strategy_policy.py`

## Resolution
- Add explicit scanner request validation with deterministic error reporting.
- Enforce validation before scanner execution to prevent invalid universe requests.
- Normalize session labels in watchlist selection to align strategy policy allowlists with scanner session taxonomy.
- Add tests to certify the contract enforcement path.

## Evidence
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/BLOCKER_01/compileall.txt`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/BLOCKER_01/pytest.txt`
