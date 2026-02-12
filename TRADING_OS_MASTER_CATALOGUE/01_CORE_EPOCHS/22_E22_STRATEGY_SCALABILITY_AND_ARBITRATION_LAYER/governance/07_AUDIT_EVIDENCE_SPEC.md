
# E22 Audit Evidence Specification

## Evidence directory
`TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/E22_STRATEGY_SCALABILITY_AND_ARBITRATION_LAYER/`

## Required evidence files
- `verification_output.json`
  - includes: epoch, generated_at_utc, valid, violations[], metrics
- `verification_summary.md`
  - human-readable summary
- `EVIDENCE_INDEX.json`
  - byte sizes + file list
- `certification_verdict.json`
  - epoch + verdict + date_utc + reasons[] + evidence[]

## Required metrics (minimum)
- strategies_enabled_count
- strategies_executed_count
- arbitration_intents_total
- arbitration_intents_allowed
- arbitration_intents_suppressed
- suppression_counts_by_reason_code
- per-cycle latency by stage (scheduler/coordinator/arbitrator)
- cache_hit_rates (if implemented)
- budgets_consumed_per_strategy

## Trace semantics
Every arbitration decision must emit at least one TRACE event:
- stage=`ARBITRATION`
- includes cycle_id, run_mode, strategy_key(s) involved, allowed_count, suppressed_count
