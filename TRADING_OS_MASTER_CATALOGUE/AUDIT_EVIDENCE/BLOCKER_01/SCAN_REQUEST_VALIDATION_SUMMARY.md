# BLOCKER_01 — Scanner Request Validation Consolidation

## Scope
- Added scanner request validation to guard malformed requests.
- Early reject payload prevents provider connection when validation fails.
- Added test coverage for validation and early rejection.
- Normalized session labels for watchlist selection to align `REG`/`RTH` parity.

## Evidence
- Source: `src/scanner/scanner_contract.py`
- Runner: `src/scanner/scanner_runner.py`
- Session normalization: `src/strategies/ross_momentum/strategy_policy.py`
- Tests: `tests/test_scanner_request_validation.py`
- Verification: `compileall.txt`, `pytest.txt`
