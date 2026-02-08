# E15_FAILURE_MODES — MANDATORY VERIFICATION COMMANDS

Codex must run and pass ALL of the following:

1. compileall
2. pytest (entire suite)
3. verify_system_reality.py (or latest equivalent)
4. Manual run:
   python -m src.main --mode SIM
   python -m src.main --mode PAPER
   python -m src.main --mode READ_ONLY
   python -m src.main --mode LIVE (execution disabled)

Failures must be fixed before proceeding.

END
