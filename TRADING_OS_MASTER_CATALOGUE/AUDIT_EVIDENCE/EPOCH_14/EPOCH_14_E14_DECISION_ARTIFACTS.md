# EPOCH 14 — Decision Artifacts (E14)

## Summary
E14 focuses on explicit, deterministic decision artifacts that are traceable and replay-safe. This audit records the canonical decision model, the orchestration flow that emits decisions, and the safety gates preventing execution without a decision artifact.

## Scope
- `src/core/intent.py`
- `src/models/data_models.py`
- `src/risk/risk_engine.py`
- `src/execution/execution_engine.py`
- `src/storage/`
- `tests/test_decision_artifacts_epoch14.py`

## Decision Artifact Coverage
- Canonical `DecisionArtifact` model introduced alongside `TradeIntent` + `RiskDecision` updates.
- `build_decision_artifact(...)` computes deterministic decision ids from ordered intents and metadata.
- Orchestrator emits `DECISION_ARTIFACT_CREATED` and trace entries before risk evaluation.
- Risk and execution layers enforce the decision artifact requirement.
- TradeRecord persistence now includes `decision_output_json` for replay and audit.

## Required Tests
- Decision determinism test: `tests/test_decision_artifacts_epoch14.py::test_decision_artifact_determinism`.
- Strategy → decision → execution smoke test: `tests/test_decision_artifacts_epoch14.py::test_strategy_decision_execution_smoke`.
- Replay safety test (no decision → no execution): `tests/test_decision_artifacts_epoch14.py::test_replay_safety_blocks_without_decision_artifact`.

## Evidence
Command outputs are captured in this folder:
- `python -m compileall src` → `compileall.txt`
- `pytest` → `pytest.txt`

## Notes
- Execution is blocked when a decision artifact is missing, enforcing explicit decisions before any order routing.
