# Acceptance Criteria

E25 is **CERTIFIED** only if all criteria are met:

## Functional

- `python -m compileall src` exits 0.
- `pytest -q` passes (or preserves existing skips).
- `python -m src.core_engine.orchestrator --mode READ_ONLY --cycles 1` runs without import/runtime errors.

## Architectural

- `src/cli/*` are runnable via `python -m src.cli.<module>` (not via file path).
- Import boundary purity: `python -c "import src; import src.core_engine.orchestrator"` succeeds without IBKR.

## Evidence

- Add `AUDIT_EVIDENCE/E25_architecture_realignment_report.json`
  - includes summary of moves, boundary enforcement, and verification outputs.
- Update `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` with E25 status.
