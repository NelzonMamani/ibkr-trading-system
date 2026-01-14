# PHASE_27_PATTERN_AGGREGATION_AND_CONFLICT_RESOLUTION

## Objective
Implement the **pattern evaluator/aggregator** that:
- runs enabled patterns
- collects `PatternResult`s
- ranks results by confidence
- produces best-long / best-short summaries
- surfaces conflicts and conservative veto flags

## Scope
### In-Scope
- Pattern registry execution pipeline
- Ranking rules (Phase 1 conservative):
  - confidence score primary
  - liquidity quality and volume confirmation adjust confidence via tags
- Conflict detection:
  - conflict when high-confidence long and short both exist in the same window
- Veto flags (do not block; surface clearly):
  - wide spread
  - degraded data quality
  - extreme low-float risk tags

### Out-of-Scope
- Portfolio-level risk decisions (Risk module)
- Any order placement

## Files to Create/Modify (Repo)
- Create: `src/strategies/ross_momentum/patterns/pattern_evaluator.py`
- Modify: `src/strategies/ross_momentum/patterns/pattern_registry.py` (enabled patterns list)

## Definition of Done
- Evaluator returns a deterministic summary object containing:
  - `all_results` (list)
  - `best_long_setup` (optional)
  - `best_short_setup` (optional)
  - `conflict_flag` (bool)
  - `combined_rationale_text`
- Conflicts and veto flags are explained in logs.
