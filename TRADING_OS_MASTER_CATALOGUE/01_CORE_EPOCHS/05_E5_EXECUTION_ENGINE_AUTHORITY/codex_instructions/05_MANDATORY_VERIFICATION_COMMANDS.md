# Mandatory Verification Commands — E5

All must pass before certification.

## Static
python -m compileall src

## Tests
pytest tests/test_execution_intent_modes.py
pytest tests/test_ibkr_readonly.py
pytest tests/test_order_gateway_retry.py
pytest tests/test_liquidity_execution.py
pytest tests/test_exit_precedence.py

## Runtime smoke (non-destructive)
RUN_SIMULATION.ps1
RUN_PAPER_TRADING.ps1
RUN_LIVE_READ_ONLY.ps1

Expected:
- No orders submitted in READ_ONLY
- PAPER executes without broker errors
- SIM deterministic across runs
