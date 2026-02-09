# M2 Contract Registry Verification Commands

1) python -m compileall -q src > TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/compileall.txt 2>&1
2) pytest -q tests/metadata -q > TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/pytest.txt 2>&1
3) pytest -q > TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/pytest_full.txt 2>&1
4) python verification_scripts/verify_m2_contract_registry.py --output-json TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/verification_output.json --output-md TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/verification_summary.md
