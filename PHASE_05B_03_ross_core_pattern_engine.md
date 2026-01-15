# PHASE_05B_03_ross_core_pattern_engine

Date: 2026-01-15

## Objective
Implement the Ross Momentum Phase-1 core pattern engine with standardized PatternResult outputs and clear explanations.

## Inputs (Must Read)
- MODULE_REQUIREMENTS_patterns.md
- ROSS_MOMENTUM_PATTERN_DETECTION_BLUEPRINT.md
- ROSS_MOMENTUM_PATTERN_REFERENCE.md
- EPOCH_05_GOVERNANCE.md (no silent mutation, determinism)

## Allowed Files (Strict)
- src/strategies/ross_momentum/patterns/pattern_base.py
- src/strategies/ross_momentum/patterns/pattern_types.py
- src/strategies/ross_momentum/patterns/pattern_registry.py
- src/strategies/ross_momentum/patterns/pattern_evaluator.py
- src/strategies/ross_momentum/patterns/momentum_patterns.py
- src/strategies/ross_momentum/patterns/breakout_patterns.py
- src/strategies/ross_momentum/patterns/pullback_patterns.py
- src/utils/validation.py (schema validation only)
- src/utils/logging.py (pattern log helpers only)

## Patterns Required (Phase 1)
1. Premarket High Break / ORB
2. Micro Pullback
3. Bull Flag
4. Consolidation Breakout
5. Failed Breakout (filter/exit warning)
Plus VWAP tags for context.

## Tasks
1. Implement PatternInputs and PatternResult contracts (as dataclasses or equivalent).
2. Ensure each pattern returns:
   - detected (bool) and rejection reason if not detected
   - direction, confidence, rationale_text
   - optional entry_zone, stop_suggestion, target_suggestion
   - setup_quality_tags, risk_flags, data_quality_flags
3. Implement pattern registry and evaluator:
   - runs enabled patterns
   - ranks by confidence
   - outputs best long/short and conflict flag

## Commands (Mandatory)
From repo root:
1. `python -m src.strategies.ross_momentum.patterns.pattern_evaluator --symbol TEST --mode SIM`
(If a different harness exists, use it; do not skip providing a runnable standalone entrypoint.)

## Required Console Output
- For each pattern:
  - detected/not detected line with short reason
- Summary:
  - best setup + confidence + rationale summary

## Acceptance Checklist
- Patterns run standalone without requiring full system orchestration.
- Outputs are deterministic for identical inputs.
- No orders are placed; only PatternResults are produced.

## Rollback Rule
Do not add extra patterns beyond the Phase-1 set in this phase.

END.
