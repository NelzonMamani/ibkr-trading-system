# 99 — CODEX MASTER INSTRUCTION BLOCK (PHASE 5)

Purpose: execute PHASE 5 (Runtime Alignment & Stress Validation) exactly as specified by this folder.

You MUST read and follow these files in order:

1) `00_READ_FIRST.md`
2) `01_PHASE_OBJECTIVE_AND_SCOPE.md`
3) `02_RUNTIME_ALIGNMENT_WORKPLAN.md`
4) `03_STRESS_AND_FAULT_INJECTION_MATRIX.md`
5) `04_EVIDENCE_REQUIREMENTS.md`
6) `05_ACCEPTANCE_CRITERIA.md`

## Constraints

- Additive changes only.
- Do not weaken governance lock.
- Do not change strategy policy content unless an explicit change-control exception is documented and approved.

## Required outputs

- A PR branch named: `codex/phase-5-runtime-alignment-and-stress-validation`
- Evidence committed under: `AUDIT_EVIDENCE/phase_5/`
- If code changes are needed:
  - prefer new verification scripts under `verification_scripts/`
  - prefer new tests under `tests/` (or strategy-local tests where appropriate)

## Mandatory commands (must run and attach logs)

- `python -m compileall src`
- `pytest -q`
- Policy audit counts command from Workplan section B
- Any runtime alignment verification command you create

## Stop condition

Stop once:
- All acceptance criteria in `05_ACCEPTANCE_CRITERIA.md` are met
- Evidence exists and is committed
- PR is opened with a clear summary and verification section

END
