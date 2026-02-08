# FILE: 05_MANDATORY_VERIFICATION.md
# TITLE: Mandatory Verification Commands (E21)
Date: 2026-02-08

Run from repo root (adapt paths if needed):

1) Compile:
   - python -m compileall src

2) Unit tests:
   - pytest -q

3) SIM lifecycle (minimum):
   - python -m src.main --mode SIM --cycles 3 --strategy ross_momentum

4) PAPER lifecycle (minimum):
   - python -m src.main --mode PAPER --cycles 3 --strategy ross_momentum
   - Confirm at least one order intent reaches execution provider when EXECUTION_ENABLED=true (paper broker)

5) LIVE read-only safety:
   - python -m src.main --mode LIVE --cycles 1 --strategy ross_momentum
   - Confirm EXECUTION_ENABLED=false blocks orders but still produces decisions and trace logs.

Expected logs must show:
- Watchlist generation K=15 or empty valid
- For any emitted intent: SF_* + XL_* + C/K snapshot present

END
