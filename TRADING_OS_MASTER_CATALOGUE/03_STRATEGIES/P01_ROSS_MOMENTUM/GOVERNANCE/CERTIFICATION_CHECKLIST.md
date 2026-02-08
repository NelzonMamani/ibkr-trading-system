# P01_ROSS_MOMENTUM — CERTIFICATION CHECKLIST (E19/E21)
Date: 2026-02-08

## A) Completeness (NO PARTIALS)
- [ ] Every canonical SF_* is classified (ALLOWED/OPTIONAL/DENIED) for Ross (no blanks).
- [ ] Every E18 XL_* trigger is classified (REQUIRED/OPTIONAL/DENIED) for Ross.
- [ ] Ross declares required C_* and K_* sets and maps them per setup family.
- [ ] Ross declares candlestick primitive usage (SCP_*, MCP_*) or explicitly denies/ignores.

## B) Policy Authority
- [ ] All tunables reside in `strategy_policy.py` (no hidden constants).
- [ ] Policy has clear units and comments for each threshold.

## C) Implementation Alignment
- [ ] Orchestrator provides StrategyContext fields required by policy (timeframes, levels, indicators).
- [ ] Runner arms XL_* triggers only after C_* and K_* gates pass.
- [ ] TradeIntent includes SF/XL IDs and traceability payload (E14/M4).

## D) Verification (E21)
Minimum verification commands (repo-specific):
- [ ] `python -m compileall src`
- [ ] `pytest -q`
- [ ] `python -m src.main --mode SIM --cycles 3 --strategy ross_momentum`
- [ ] `python -m src.main --mode PAPER --cycles 3 --strategy ross_momentum` (must place simulated orders if EXECUTION_ENABLED)
- [ ] `python -m src.main --mode LIVE --cycles 1 --strategy ross_momentum` with EXECUTION_ENABLED=false (read-only path)

Expected outcomes:
- [ ] Watchlist K=15 is produced or empty correctly (per contract).
- [ ] No-trade contexts correctly produce zero intents.
- [ ] At least one SF/XL path can produce an intent in SIM/PAPER with deterministic trace log.

END
