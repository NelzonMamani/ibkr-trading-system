# EPOCH 05 — STRATEGY EXECUTION GOVERNANCE (UPDATED)

This update formalizes Track A: Ross Momentum as the first fully automated live strategy.

## Scope
- Strategy constitutions live under `src/strategies/*`
- Orchestrator consumes StrategyPolicy and builds StrategyContext
- StrategyRunner evaluates Policy × Context

## Live Authority
- Market session authority: America/New_York
- Operator display: UTC and Europe/London
- DST handled via exchange calendar

## Completion Criteria
- All Track A phases executed successfully
- Paper trading parity with SIM
- Live trading gated by RiskEngine and StopController

Status: READY FOR CODEX EXECUTION
