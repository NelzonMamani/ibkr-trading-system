FILE: 99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: EXECUTE STRATEGY CERTIFICATION FRAMEWORK V2

CONTEXT:

Institutional Strategy Certification Framework V2 has been introduced under:

TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/05_STRATEGY_CERTIFICATION_FRAMEWORK_V2/

OBJECTIVE:

1. Replace legacy STRATEGY_AUDIT_MATRIX.md with STRATEGY_AUDIT_MATRIX_V2.md.
2. Update audit generator to enforce ALL V2 controls.
3. Re-run certification audit for P01–P20.
4. Update:
   - STRATEGY_CERTIFICATION_REPORT.md
   - STRATEGY_AUDIT_MATRIX_V2 results
   - SYSTEM_STATE_CERTIFIED.md

RULES:

- No behavioral changes.
- SPEC-ONLY governance updates.
- Missing REQUIRED control = FAIL.
- Do not auto-pass sections.
- Produce deterministic audit output.
- Preserve previous evidence.

DELIVERABLES:

- Updated matrix file
- Updated certification report
- Updated system state
- Summary diff

STOP once audit is complete.

END
