# Mandatory Verification Commands — E7

All must pass.

## Static
python -m compileall src

## Tests
pytest tests/test_execution_intent_modes.py
pytest tests/test_read_only_guard.py
pytest tests/test_runtime_wiring.py
pytest tests/test_orchestrator_shutdown.py

## Current verification boundary (2026-11-14)

Run the affected tests above with the existing offline transport guard, following
[the current runbook](../../../../RUNBOOK.md). The former root live/PAPER runtime
wrappers are retired; writable PAPER smoke is not non-destructive verification.
Mode parity and operational certification require their own bounded authorized
proofs. Historical audit outputs remain unchanged and are not rerun or upgraded.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
