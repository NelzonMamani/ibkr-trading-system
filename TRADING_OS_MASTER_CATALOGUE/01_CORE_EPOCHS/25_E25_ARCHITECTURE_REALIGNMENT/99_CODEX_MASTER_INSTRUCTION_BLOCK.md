# 99 — CODEX MASTER INSTRUCTION BLOCK (E25)

You are executing **E25_ARCHITECTURE_REALIGNMENT**.

## Hard rules

- Read all GOVERNANCE documents first.
- Preserve system behavior and keep the test suite green.
- Apply changes incrementally, verifying after each batch.
- Do not perform massive directory moves unless strictly necessary.
- Any adapter imports in core at import-time must be eliminated (lazy import behind runtime bootstrap).

## Execution steps

1) Gap analysis
- Follow `CODEX_INSTRUCTIONS/01_REALITY_GAP_ANALYSIS.md`.
- Write `AUDIT_EVIDENCE/E25_gap_analysis.json`.

2) Implement migration
- Follow `CODEX_INSTRUCTIONS/02_RESTRUCTURE_PLAN.md` and `03_MIGRATION_SEQUENCE.md`.
- Primary target: CLI module invocation correctness and import boundary purity.

3) Verify
Run all commands in `CODEX_INSTRUCTIONS/04_VERIFICATION_COMMANDS.md`.
Capture exit codes and summaries.

4) Evidence + certification
- Write `AUDIT_EVIDENCE/E25_architecture_realignment_report.json`.
- Update `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` to include:
  - `E25_ARCHITECTURE_REALIGNMENT: CERTIFIED`

## Completion criteria

E25 is complete only if:
- `python -m compileall src` passes
- `pytest -q` passes
- orchestrator help + cycle runs without import/runtime errors
- `python -m src.cli.submit_one_order --help` works

Stop if any step threatens safety invariants; prefer adding compatibility shims over breaking imports.
