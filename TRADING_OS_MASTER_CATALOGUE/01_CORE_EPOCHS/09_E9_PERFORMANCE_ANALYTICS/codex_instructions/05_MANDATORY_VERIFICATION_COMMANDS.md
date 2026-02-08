# Mandatory Verification Commands — E9

All must pass.

## Static
python -m compileall src

## Tests
pytest tests/test_analytics_metrics.py
pytest tests/test_analytics_attribution.py
pytest tests/test_analytics_determinism.py
pytest tests/test_analytics_missing_data.py

## Offline recompute
python scripts/recompute_analytics.py --from-ledger --deterministic

Expected:
- Deterministic results
- Correct metrics for known fixtures
- Explicit flags for missing data
