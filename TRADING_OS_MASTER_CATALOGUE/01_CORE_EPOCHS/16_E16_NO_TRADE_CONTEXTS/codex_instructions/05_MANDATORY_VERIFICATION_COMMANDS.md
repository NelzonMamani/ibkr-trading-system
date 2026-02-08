# E16_NO_TRADE_CONTEXTS — MANDATORY VERIFICATION

Codex must run and pass ALL of the following:

1. compileall
2. pytest (full suite)
3. verify_system_reality.py (or latest)
4. Manual runs:
   python -m src.main --mode SIM
   python -m src.main --mode PAPER
   python -m src.main --mode READ_ONLY
   python -m src.main --mode LIVE (execution disabled)

All no-trade contexts must prevent execution.

END
