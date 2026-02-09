# EPOCH 15 — Failure Modes (E15)

## Summary
E15 hardens the fault taxonomy and deterministic recovery matrix. The system now exposes a canonical fault policy snapshot, maps every fault category to a severity and containment rule, and uses a single recovery action matrix per run mode to avoid silent degradation.

## Scope
- `src/core/faults.py`
- `src/core/orchestrator.py`
- `tests/test_epoch15_17_safety_cluster.py`

## Failure Mode Coverage
- Canonical taxonomy defined via `FAULT_TAXONOMY`, including severity and containment notes.
- Deterministic recovery action matrix (`RECOVERY_ACTION_MATRIX`) keyed by run mode.
- Unknown faults default to CRITICAL severity and HALT/ABORT actions.
- Audit snapshot available through `fault_policy_snapshot()` for evidence capture.

## Required Tests
- Fault policy snapshot coverage: `tests/test_epoch15_17_safety_cluster.py::test_fault_policy_snapshot_covers_categories`.

## Evidence
Command outputs are captured in this folder:
- `python -m compileall src` → `compileall.txt`
- `pytest tests/test_epoch15_17_safety_cluster.py` → `pytest.txt`

## Notes
- Fault handling remains deterministic via the orchestrator’s existing `_handle_fault` path.
