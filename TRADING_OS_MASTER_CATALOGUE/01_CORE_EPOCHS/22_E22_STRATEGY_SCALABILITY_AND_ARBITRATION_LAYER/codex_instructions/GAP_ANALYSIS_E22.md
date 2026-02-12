# GAP_ANALYSIS_E22

## Contract mapping (governance -> repo reality)

### STRATEGY_SCHEDULING_CONTRACT
- **Partially satisfied**
- Evidence: deterministic sorting exists in `src/strategy_portfolio/arbitration.py` and config toggles exist in `src/config/config_registry.py`.
- Missing: explicit strategy scheduling cap, per-strategy intent budget enforcement at orchestrator aggregation point.

### SHARED_DATA_COORDINATION_CONTRACT
- **Partially satisfied**
- Evidence: scanner/provider coordination, market data hub, and deterministic cycle-level processing exist.
- Missing: E22-specific shared-data coordinator contract object and explicit E22 provenance-tag emission.

### INTENT_ARBITRATION_CONTRACT
- **Partially satisfied**
- Evidence: symbol arbitration helper exists (`src/strategy_portfolio/arbitration.py`), intent normalization exists (`_normalize_trade_intents`).
- Missing: orchestrator-wired arbitration artifact with reason-coded suppressions and configurable caps.

### ARBITRATION_EVIDENCE_CONTRACT
- **Missing**
- Evidence: no dedicated E22 evidence verifier/output directory yet.
- Missing: dedicated E22 verifier generating required files and deterministic outputs.

### STRATEGY_SCALABILITY_HEALTH_CONTRACT
- **Missing**
- Evidence: no E22 metrics bundle for suppressed counts / strategy scheduling order in dedicated verifier output.

## Minimal additive patch plan
1. Add new `src/e22/strategy_scalability_and_arbitration.py` with scheduler, arbitrator, artifact dataclasses, and default-off apply helper.
2. Add E22 config entries to `src/config/config_registry.py` with defaults keeping behavior unchanged.
3. Wire E22 only at orchestrator post-normalization, pre-risk aggregation point in `src/core/orchestrator.py`.
4. Add unit/integration-ish tests for determinism, conflict resolution, cap enforcement, and disabled non-regression.
5. Add verifier script `verification_scripts/verify_e22_strategy_scalability_and_arbitration.py` that writes deterministic E22 evidence bundle and updates system state via canonical helper when certified.
