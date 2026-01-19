# ADAPTIVE_REGIME_MICROSTRUCTURE_LAYER — Read Order (Codex)
Last updated: 2026-01-19

## Goal
Implement a complete, deterministic Adaptive Regime / Microstructure Layer that:
- Runs in SIM and LIVE_READ_ONLY with identical behaviour given the same inputs
- Never mutates or overrides strategy rules silently
- Produces structured regime artifacts that downstream components can consume
- Is fully wired into the existing Trading OS pipeline with tests and docs

## What Codex must do
1. Read and obey project governance hierarchy (SYSTEM_CONSTITUTION → SYSTEM_STATE → README).
2. Implement the phases in order below.
3. For each phase:
   - Add code + tests
   - Add/extend event schemas
   - Ensure deterministic outputs under replay where applicable
   - Keep all new behaviour behind explicit config toggles (safe-by-default)

## Required read order
1) 01_OVERVIEW_AND_DESIGN_CONSTRAINTS.md
2) 02_PHASE_1_REGIME_TAXONOMY_AND_CONTRACTS.md
3) 03_PHASE_2_OBSERVERS_PURE_MEASUREMENT.md
4) 04_PHASE_3_STATISTICAL_BASELINES.md
5) 05_PHASE_4_REGIME_CLASSIFIER.md
6) 06_PHASE_5_STRATEGY_INTERACTION_LAYER.md
7) 07_PHASE_6_STORAGE_AND_EVENT_SCHEMA.md
8) 08_PHASE_7_TESTS_DETERMINISM_AND_REPLAY.md
9) 09_PHASE_8_DOCS_RUNBOOK_AND_HOUSEKEEPING.md

## Output expectation
After Phase 8, the system must:
- Emit a REGIME_SNAPSHOT event each cycle (when enabled)
- Emit a REGIME_POLICY_DECISION event when applying a regime policy to intents
- Persist regime artifacts in storage alongside TradeRecord
- Provide a CLI/entry-point switch to enable the layer in SIM and LIVE_READ_ONLY safely
