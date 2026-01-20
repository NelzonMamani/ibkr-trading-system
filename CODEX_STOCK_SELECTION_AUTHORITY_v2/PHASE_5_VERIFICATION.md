PHASE 5 — VERIFICATION & SAFETY

Codex must run and report:

1) python -m compileall -q src
2) pytest -q
3) python -m src.main --mode SIM --cycles 1
4) python -m src.main --mode PAPER --cycles 1
5) python -m src.main --mode LIVE_MICRO --cycles 1

Expected:
- LIVE_MICRO halts on deterministic feed
- SIM/PAPER run fully
- No policy mismatches

Deliverable:
docs/PR_VERIFICATION_REPORT.md
