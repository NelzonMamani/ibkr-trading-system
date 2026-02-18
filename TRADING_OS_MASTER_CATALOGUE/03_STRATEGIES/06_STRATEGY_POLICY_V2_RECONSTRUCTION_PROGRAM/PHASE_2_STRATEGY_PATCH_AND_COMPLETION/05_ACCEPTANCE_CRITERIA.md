# 05 — Acceptance Criteria (Phase 2)

Phase 2 is complete only when all are true:

- `python -m compileall src` succeeds
- `pytest -q` passes
- Matrix V2 shows for P01–P20:
  - Verdict: CERTIFIED
  - Domains D0–D14: PASS or legitimate NOT_APPLICABLE with explicit rationale
- Certification report shows Missing controls: None for all strategies
- P01 remains CERTIFIED (non-regression)
