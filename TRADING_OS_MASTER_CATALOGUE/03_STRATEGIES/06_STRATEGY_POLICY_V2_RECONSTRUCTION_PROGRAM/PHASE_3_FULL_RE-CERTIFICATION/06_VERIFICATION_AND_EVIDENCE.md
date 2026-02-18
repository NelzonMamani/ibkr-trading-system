# VERIFICATION & EVIDENCE

Required commands:

python -m compileall src
pytest -q
python - <<'PY'
from src.metadata.strategy_policy_v2_audit import generate_audit_artifacts
results = generate_audit_artifacts()
print({v: sum(1 for r in results if r.verdict == v) for v in ['CERTIFIED','CONDITIONALLY_CERTIFIED','FAIL']})
PY

Evidence artifacts:
- STRATEGY_AUDIT_MATRIX_V2.md
- STRATEGY_CERTIFICATION_REPORT.md
- SYSTEM_STATE_CERTIFIED.md

END
