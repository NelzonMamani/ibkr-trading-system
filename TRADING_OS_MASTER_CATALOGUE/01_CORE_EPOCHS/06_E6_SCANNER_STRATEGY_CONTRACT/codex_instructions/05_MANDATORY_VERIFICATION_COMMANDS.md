# Mandatory Verification Commands — E6

All must pass.

## Static
python -m compileall src

## Tests
pytest tests/test_scanner_contract.py
pytest tests/test_scanner_watchlist_artifact_empty.py
pytest tests/test_scanner_pct_change_fallback.py
pytest tests/test_scanner_policy_from_strategy.py

## Runtime (safe)
RUN_SIMULATION.ps1
RUN_PAPER_TRADING.ps1

Expected:
- Scanner outputs facts only
- Empty outputs do not error
- Session semantics logged explicitly
