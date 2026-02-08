# P02 — CODEX INSTRUCTIONS — 02_REQUIRED_MAPPINGS
You MUST ensure the strategy declares and utilises:
- Setup Families: explicit ALLOWED/OPTIONAL/DENIED lists
- Execution Triggers: explicit ALLOWED/DENIED lists and mapping SF → XL
- Conditions: REQUIRED C_* list enforced prior to intent emission
- Confirmations: REQUIRED K_* list enforced; OPTIONAL K_* mapped per SF/mode
- Patterns: SCP_*/MCP_* utilised only as inputs to confirmations/setup activation
- Levels/Zones/Invalidations: LVL/ZONE required per SF/XL; INV_* defined per entry

Deliverables required (must exist in repo under P02 folder):
- `GOVERNANCE/*` files already provided
- A `strategy_policy.py` that contains ALL tunable knobs and registry mappings
- Strategy-local tests under `src/strategies/statistical_intraday_momentum/tests`

END
