
# 03_IMPLEMENTATION_TASKS — E22

Implement minimal, additive E22 layer.

## Required deliverables (code)
1) `StrategyScheduler` (or equivalent)
- stable ordering by strategy priority
- per-strategy budgets (configurable)
- emits budget consumption metrics

2) `IntentArbitrator`
- deterministic ordering and tie-breakers
- symbol exclusivity policy (configurable)
- suppression reason codes

3) `ArbitrationDecisionArtifact`
- JSON schema (dataclass / pydantic / dict)
- MD summary writer

4) `E22 Verifier`
- `verification_scripts/verify_e22_strategy_scalability_and_arbitration.py`
- writes evidence into:
  `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/E22_STRATEGY_SCALABILITY_AND_ARBITRATION_LAYER/`

5) Integration wiring
- Insert E22 at the single canonical aggregation point:
  strategy intents -> E22 -> risk/execution

## Configuration
Add explicit config entries (with hard/optional classification consistent with repo):
- enable/disable E22
- default priorities
- budgets
- symbol exclusivity
- max intents per cycle (global cap)

## Tests
- Unit tests for deterministic arbitration ordering
- Integration test: two dummy strategies with conflicting intents -> verify winner + suppression reason codes
