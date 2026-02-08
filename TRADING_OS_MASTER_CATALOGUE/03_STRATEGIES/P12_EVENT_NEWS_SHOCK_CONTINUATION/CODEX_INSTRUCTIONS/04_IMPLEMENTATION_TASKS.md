# P12_EVENT_NEWS_SHOCK_CONTINUATION — CODEX — 04_IMPLEMENTATION_TASKS
You MUST:
1) Create full strategy module under `src/strategies/` (new; does not exist yet)
2) Implement exhaustive `strategy_policy.py` with:
   - stock selection tunables
   - SF/XL/C/K/SCP/MCP/LVL/ZONES/INV mapping tables
3) Implement runner logic producing TradeIntents with SF/XL/C/K/INV trace fields
4) Implement strategy-local tests
5) Wire into strategy factory/orchestrator via E19 contracts
6) Run mandatory verification and write PR_VERIFICATION_REPORT.md

Stop only when checklist is fully green.

END
