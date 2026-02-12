# REALITY_MAP_E22

## Runtime pipeline reality
- Orchestration entrypoint is `CoreOrchestrator.run_cycle` in `src/core/orchestrator.py`.
- Strategy fan-in currently happens in this sequence:
  1. `StrategyRunner.generate_trade_intents(...)`
  2. `StrategyRunner.run_from_intents(...)`
  3. `CoreOrchestrator._merge_trade_intents(...)`
  4. `CoreOrchestrator._normalize_trade_intents(...)`
- Risk handoff currently happens by iterating normalized `TradeIntent` values and calling `RiskEngine.evaluate_trade_intent(...)` per intent.
- Execution handoff then iterates risk decisions into `ExecutionEngine.execute_trade(...)`.

## Existing arbitration / allocation reality
- Existing strategy arbitration primitives already exist in `src/strategy_portfolio/arbitration.py` (`arbitrate_symbol`, `arbitrate_all`) and are deterministic by sorted keys.
- Existing allocation primitives already exist in `src/strategy_portfolio/allocation.py` (`allocate`, `compute_global_risk_budget`).
- Current orchestrator path does **not** centrally apply multi-strategy arbitration before risk.

## Config + feature flags
- Config is registry-driven (`src/config/config_registry.py`) with default values and env overrides.
- Existing feature-gate pattern uses booleans with default `False` for additive behavior (example: `ADAPTIVE_REGIME_LAYER_ENABLED`, `INTENT_DEDUP_SELFTEST_ENABLED`).
- Run-mode semantics are governed by `RUN_MODE`/`RUN_MODE_EFFECTIVE` with values `SIM`, `PAPER`, `READ_ONLY`, `LIVE`.

## Audit evidence patterns
- Verification scripts follow deterministic evidence output patterns under `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/...`.
- Canonical evidence files include `compileall.txt`, `pytest_full.txt`, `verification_output.json`, `verification_summary.md`, `EVIDENCE_INDEX.json`, and `certification_verdict.json`.
- System-state updates are handled via canonical helper `update_system_state_statuses` in `src/metadata/m0_canon_helpers.py` from verifier scripts.

## Minimal insertion point for E22
- Minimal additive insertion point is immediately after `_normalize_trade_intents(...)` and immediately before risk iteration in `CoreOrchestrator.run_cycle`.
- This location allows E22 to:
  - observe aggregated strategy intents,
  - apply deterministic arbitration and caps,
  - emit structured arbitration audit event,
  - remain non-interfering when feature-flag disabled.
