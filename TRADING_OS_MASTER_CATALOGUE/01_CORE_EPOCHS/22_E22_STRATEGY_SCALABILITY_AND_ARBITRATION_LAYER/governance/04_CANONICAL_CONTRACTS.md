
# E22 Canonical Contracts

This epoch introduces contracts. Names here are conceptual; implementers map them onto existing modules.

## Contract 1 — STRATEGY_SCHEDULING_CONTRACT
Defines:
- how strategies are selected for a cycle
- deterministic ordering rules
- budgets and enforcement semantics
- what happens when a budget is exceeded

### Required fields
- `strategy_key`
- `enabled` (bool)
- `priority` (int; higher = earlier)
- `budget`:
  - `max_snapshots_per_cycle`
  - `max_bar_requests_per_cycle`
  - `max_scanner_requests_per_cycle`
  - `max_compute_ms_per_cycle`
- `determinism`:
  - stable ordering key list

### Enforcement
Budget breach must:
- mark strategy as `DEGRADED_FOR_CYCLE`
- emit audit event `E22_BUDGET_BREACH`
- optionally skip strategy evaluation (policy flag)

## Contract 2 — SHARED_DATA_COORDINATION_CONTRACT
Defines:
- request types eligible for coalescing
- cache TTL, provenance, and invalidation
- how strategies request data (through coordinator API, not direct broker calls in normal path)

### Required invariants
- no strategy may exceed global market data caps indirectly
- coordinator tags payloads with provenance (M10 compatibility)
- coordinator emits “data_quality flags” for missing fields

## Contract 3 — INTENT_ARBITRATION_CONTRACT
Defines:
- input: list of intents with metadata:
  - `strategy_key`, `symbol`, `side`, `confidence`, `risk_cost`, `time_in_force`, etc.
- output:
  - `allowed_intents[]`
  - `suppressed_intents[]` with reason codes

### Minimum reason codes
- `DUPLICATE_INTENT`
- `SYMBOL_EXCLUSIVITY_CONFLICT`
- `PORTFOLIO_EXPOSURE_LIMIT`
- `RISK_ENGINE_DENY`
- `RUN_MODE_DENY`
- `BUDGET_DENY`
- `DATA_QUALITY_DENY`
- `TIE_BREAK_LOSS`

## Contract 4 — ARBITRATION_EVIDENCE_CONTRACT
Evidence files per run/cycle:
- `arbitration_report.json` (machine)
- `arbitration_report.md` (human)
- `EVIDENCE_INDEX.json` (index with byte sizes + generated timestamp)

Evidence must be deterministic excluding timestamps.

## Contract 5 — STRATEGY_SCALABILITY_HEALTH_CONTRACT
Defines health metrics:
- per-cycle latency by stage
- budgets consumed
- cache hit rates
- number of suppressed intents by reason code
