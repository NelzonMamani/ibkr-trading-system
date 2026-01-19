# ADAPTIVE_REGIME_MICROSTRUCTURE_LAYER — Phase Index
Last updated: 2026-01-19

## Phase map
- Phase 1: Regime taxonomy & contracts
- Phase 2: Observers (pure measurement)
- Phase 3: Statistical baselines
- Phase 4: Regime classifier
- Phase 5: Strategy interaction layer (policy application)
- Phase 6: Storage & event schema integration
- Phase 7: Determinism & replay safety tests
- Phase 8: Docs, runbook, housekeeping notes

## Definition of Done (Layer)
The layer is complete when:
1) It can be enabled in SIM and LIVE_READ_ONLY via config.
2) It emits REGIME_SNAPSHOT each cycle (when enabled).
3) It emits REGIME_POLICY_DECISION when policy is enabled (applied or not).
4) StrategyRunner consumes policy decisions deterministically (weights/eligibility).
5) Storage persists regime artifacts alongside TradeRecord.
6) pytest -q passes with deterministic tests added.
