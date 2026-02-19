# E24 — Async Runtime & Event Loop Governance (CODEX INSTRUCTIONS)

**Generated:** 2026-02-19T00:35:32Z

## Mission
Implement E24 in the existing repo with **minimal additive fixes** only.
Primary objective: eliminate Python 3.14+ event-loop import failures (notably via `eventkit`/`ib_insync`) and restore full `pytest -q` stability.

## Law
- Do not redesign the system.
- Do not rename epochs.
- Do not change strategy logic.
- Fix import-time loop safety and runtime boot determinism.
- Every change must have evidence and verification commands.

## Read Order
1. `01_REALITY_VERIFICATION_AND_GAP_ANALYSIS.md`
2. `02_IMPLEMENTATION_TASKS.md`
3. `03_MANDATORY_VERIFICATION_COMMANDS.md`
4. `04_EVIDENCE_AND_CERTIFICATION_UPDATES.md`
5. `99_CODEX_MASTER_INSTRUCTION_BLOCK.md`

