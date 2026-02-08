# LEDGER ARTIFACTS AND RETENTION

## Mandatory artifacts (append-only)
- DATA_PROVENANCE_LEDGER
  - append-only event log, queryable by symbol/time/mode/decision_id
- DATA_SOURCE_REGISTRY
  - canonical list of sources and constraints
- MODE_TRUTH_MATRIX
  - per mode: expected data sources, expected latencies, allowed fallbacks
- DATA_FRESHNESS_LOG
  - summary indexes: stale/frozen/unknown frequency
- DATA_LIMITATION_NOTES
  - catalog of recurring limitations for debugging and learning filters

## Retention and reset
- Trading-day “reset” means expiring time-bounded caches and ephemeral state,
  not erasing audit history.
- Ledger records are retained per policy (configurable), but must support:
  - daily rollups
  - pruning after retention window
  - immutable snapshots for certified periods (optional)

END
