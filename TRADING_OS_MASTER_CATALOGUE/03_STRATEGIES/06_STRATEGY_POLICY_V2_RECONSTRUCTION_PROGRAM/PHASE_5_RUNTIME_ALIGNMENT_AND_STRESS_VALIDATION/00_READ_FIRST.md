# PHASE_5_RUNTIME_ALIGNMENT_AND_STRESS_VALIDATION

This phase validates that **Strategy Policy V2** (now institutionalised and governance-locked) is **actually consumable by the runtime** across SIM/PAPER/READ_ONLY/LIVE modes, and that the platform can withstand realistic orchestration cycles without silent failure or policy drift.

## Read order

1. `01_PHASE_OBJECTIVE_AND_SCOPE.md`
2. `02_RUNTIME_ALIGNMENT_WORKPLAN.md`
3. `03_STRESS_AND_FAULT_INJECTION_MATRIX.md`
4. `04_EVIDENCE_REQUIREMENTS.md`
5. `05_ACCEPTANCE_CRITERIA.md`
6. `99_CODEX_MASTER_INSTRUCTION_BLOCK.md`

## Non‑negotiables

- **Additive fixes only** unless explicitly authorised by the phase documents.
- **No weakening of governance lock**: baseline snapshot remains authoritative.
- Evidence must be produced (logs + artifacts) and committed under `AUDIT_EVIDENCE/phase_5/`.
