
# 01_REALITY_VERIFICATION — E22

Codex must first establish current reality in the repo:

## Required actions
1) Print tree snippets for:
- orchestrator / runner entrypoints
- strategy runner(s)
- risk engine handoff
- execution engine handoff
- existing decision artifacts (if any)
- existing verification script patterns (M7/M8/M9/M10 + system_integrity script)

2) Identify:
- where `TradeIntent` (or equivalent) is defined
- where strategy outputs are aggregated
- where risk/execution receives intents/orders

3) Confirm existing run modes and gating:
- SIM, PAPER, READ_ONLY, LIVE
- any “live micro” is configuration, not a run mode

## Output required
Create `TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/<E22 folder>/CODEX_INSTRUCTIONS/REALITY_MAP_E22.md`
containing:
- discovered modules + key function names
- exact call graph for the intent pipeline
- identified insertion point for E22 arbitration
