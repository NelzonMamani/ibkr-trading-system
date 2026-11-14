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

## Current verification boundary (2026-11-14)

Run the affected tests above with the existing offline transport guard, following
[the current runbook](../../../../RUNBOOK.md). The former root live/PAPER runtime
wrappers are retired; writable PAPER smoke is not non-destructive verification.
Mode parity and operational certification require their own bounded authorized
proofs. Historical audit outputs remain unchanged and are not rerun or upgraded.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
