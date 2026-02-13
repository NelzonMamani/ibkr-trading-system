# 04_MANDATORY_VERIFICATION_COMMANDS.md
# Mandatory Verification Commands — E23
Last updated: 2026-02-13

Codex MUST run and capture evidence for:

1) Compile:
   python -m compileall src

2) Tests:
   pytest -q

3) E23 runner:
   python -m src.integrity.e23

4) Minimal boot cycles (fast, safe):
   python -m src.main --mode SIM --cycles 1
   python -m src.main --mode PAPER --cycles 1
   python -m src.main --mode READ_ONLY --cycles 1

5) Smoke: ensure READ_ONLY does not route orders even if IBKR is connected.
   (Implement a deterministic check; failing it is HARD drift.)

All evidence outputs must be saved (JSON/MD) under an audit evidence folder.

END
