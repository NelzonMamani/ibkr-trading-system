# 99 — CODEX MASTER INSTRUCTION (PHASE 1)

## Mission
Upgrade strategy policy certification to ISGS-V2 institutional grade.

## Hard Rules
- Additive changes only.
- No runtime wiring changes (brokers/execution engine untouched).
- Deterministic outputs.
- All tests must pass.
- Preserve P01 CERTIFIED.

## Tasks (Implementation)
1) Add Institutional Matrix V2 artifacts:
   - Create `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/04_STRATEGY_CERTIFICATION_AND_GOVERNANCE/STRATEGY_AUDIT_MATRIX_V2.md`
   - Keep legacy matrix if needed, but V2 is authoritative.

2) Implement audit engine module:
   - Module emits:
     - `STRATEGY_CERTIFICATION_REPORT.md`
     - `STRATEGY_AUDIT_MATRIX_V2.md`
   - Must evaluate domains D0..D9 and controls defined in Phase 1 docs.
   - Must detect default-only policies.
   - Must support NOT_APPLICABLE via explicit rationale in policy notes.

3) Add/extend pytest tests in `tests/metadata/`:
   - Institutional matrix test
   - Minimum thresholds test
   - P01 non-regression test

4) Update system state files:
   - Add STRATEGY_CERTIFICATION_PHASE field
   - Add counts summary fields

## Verification Commands (Mandatory)
Run locally:
- `python -m compileall src`
- `pytest -q`

## Evidence
Update report headers with timestamps.
Do not embed volatile environment-specific details.

## Success Criteria
- A deterministic institutional audit runs.
- Matrix v2 produced.
- Report produced.
- P01 = CERTIFIED
- P02..P20 = FAIL (expected until Phase 2)
- CI tests enforce rules.

END
