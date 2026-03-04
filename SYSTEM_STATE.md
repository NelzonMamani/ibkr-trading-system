SYSTEM_STATE.md

IBKR Trading System — Authoritative Runtime State

Last Updated: 2026-03-04
Status: ACTIVE DEVELOPMENT — LIVE READINESS HARDENING
Authority Level: Canonical (supersedes prior SYSTEM_STATE versions)

1. LIVE READINESS CRITERIA (CURRENT)

LIVE trading is considered enabled only when all are true:
- RUN_MODE=LIVE
- EXECUTION_ENABLED=true
- IBKR_ORDER_TRANSLATION_ENABLED=true
- IBKR_ORDER_SUBMISSION_ENABLED=true
- IBKR_READONLY_ENABLED=false
- IBKR_KILL_SWITCH=false
- IBKR_LIVE_PORT=7496 (hard requirement for LIVE)
- SCANNER_MODE=LIVE_READONLY (scanner remains strict)

Port policy:
- 7496 = LIVE account socket
- 7497 = PAPER account socket

2. STRATEGY ENABLEMENT (P01/P02/P03)

Canonical keys:
- ROSS_MOMENTUM_STRATEGY_ENABLED (alias: STRATEGY_ROSS_MOMENTUM_ENABLED)
- STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED (alias: STRATEGY_STATISTICAL_INTRADAY_MOMENTUM_ENABLED)
- MEAN_REVERSION_STRATEGY_ENABLED (alias: STRATEGY_MEAN_REVERSION_ENABLED)

Startup prints an explicit "Enabled strategies" banner with source/env provenance.

3. MULTI-STRATEGY ORCHESTRATION POLICY

Each enabled strategy receives its own scanner request derived from its StrategyPolicyV2/V1 policy surface.
Expected logs per cycle include:
- [ORCH][SCANNER_REQUEST] strategy=ross_momentum ...
- [ORCH][SCANNER_REQUEST] strategy=statistical_intraday_momentum ...
- [ORCH][SCANNER_REQUEST] strategy=mean_reversion ...

Per-strategy watchlist snapshots are cached and reused intra-session when a cycle yields an empty list.

4. LIVE VERIFICATION COMMANDS

- python -m compileall src
- pytest -q
- scripts/run_paper_open_smoke_trade.sh
- python verification_scripts/multi_strategy_orch_smoke.py
- scripts/run_live_open_smoke_trade.sh

Evidence roots:
- TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/multi_strategy_orch_smoke/
- TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/live_open_smoke_trade/

END OF SYSTEM_STATE.md
