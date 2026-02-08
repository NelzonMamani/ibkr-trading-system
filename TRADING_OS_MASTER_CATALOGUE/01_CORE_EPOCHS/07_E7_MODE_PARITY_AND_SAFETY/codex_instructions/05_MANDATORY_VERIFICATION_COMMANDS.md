# Mandatory Verification Commands — E7

All must pass.

## Static
python -m compileall src

## Tests
pytest tests/test_execution_intent_modes.py
pytest tests/test_read_only_guard.py
pytest tests/test_runtime_wiring.py
pytest tests/test_orchestrator_shutdown.py

## Runtime smoke
RUN_SIMULATION.ps1
RUN_PAPER_TRADING.ps1
RUN_LIVE_READ_ONLY.ps1

Expected:
- Identical behavior across modes
- No execution in LIVE_READ_ONLY
- No mode drift mid-run
