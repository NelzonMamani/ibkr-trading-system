# Mandatory Verification Commands — E8

All must pass.

## Static
python -m compileall src

## Tests
pytest tests/test_regime_classifier.py
pytest tests/test_regime_observers.py
pytest tests/test_regime_policy_application.py
pytest tests/test_regime_live_readonly_missingness.py

## Runtime (safe)
RUN_SIMULATION.ps1
RUN_PAPER_TRADING.ps1

Expected:
- Regime context present
- No execution impact
- Deterministic outputs
