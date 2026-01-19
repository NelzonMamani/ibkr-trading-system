# Phase 1 — Regime Taxonomy & Contracts
Last updated: 2026-01-19

## Objective
Introduce a stable type system for regimes and the contracts used across the OS.

## Deliverables
1) New module folder:
- src/regime/ (or src/core/regime/ if that matches existing structure; choose one and apply consistently)

2) Core contracts (dataclasses / enums) in src/regime/contracts.py:
- RegimeLabel enum (minimum set below)
- FeatureVector (typed structure; avoid dict-of-any for core path)
- RegimeSnapshot
- RegimePolicyDecision
- RegimeEvidenceItem (feature_name, value, baseline, contribution, note)
- RegimeDataQualityFlag enum

### RegimeLabel (minimum)
- OPENING_MOMENTUM
- CHOP_LOW_VOL
- TRENDING
- HIGH_VOL_RISK_OFF
- NEWS_DRIVEN
- AFTER_HOURS_THIN
- UNKNOWN

3) Event schema registration
Add new event types (names are fixed):
- REGIME_SNAPSHOT
- REGIME_POLICY_DECISION

If the repo has an event schema registry, register both with structured payload schemas.

4) Config registry additions
Add config keys to src/config/config_registry.py (or equivalent):
- ADAPTIVE_REGIME_LAYER_ENABLED (bool, default False, HARD enforced False)
- ADAPTIVE_REGIME_POLICY_ENABLED (bool, default False)
- ADAPTIVE_REGIME_MIN_CONFIDENCE_TO_APPLY (float default 0.65)
- ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE (enum: OFF|WEIGHT|ENABLE_DISABLE)
- ADAPTIVE_REGIME_MAX_RISK_MULTIPLIER (float default 1.0)
- ADAPTIVE_REGIME_MIN_RISK_MULTIPLIER (float default 0.25)
- ADAPTIVE_REGIME_ALLOWED_SESSIONS (list; default REGULAR)
- ADAPTIVE_REGIME_FEATURE_SET (enum: BASIC|EXTENDED; default BASIC)
- ADAPTIVE_REGIME_BASELINE_WINDOW (int default 60)
- ADAPTIVE_REGIME_EWMA_ALPHA (float default 0.2)

5) Tests
Add tests/test_regime_contracts.py:
- Enum stability (labels exist)
- Snapshot serialization to event payload (deterministic ordering)
- Policy decision validation (bounds)

## Acceptance criteria
- python -m src.main --mode SIM --strategy ross_momentum --cycles 1 runs unchanged when flags disabled.
- New contracts compile and tests pass.
- Event types are known (no “Unknown event_type=REGIME_*” logs when emitted later).
