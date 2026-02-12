
# 05_MANDATORY_VERIFICATION_COMMANDS — E22

Run these commands from repo root:

1) `python -m compileall -q src tests verification_scripts`
2) `python -m pytest -q`
3) `python verification_scripts/verify_e22_strategy_scalability_and_arbitration.py --allow-overwrite`
4) `python verification_scripts/system_integrity_and_capability_report.py --allow-overwrite`

If any command fails, fix before opening PR.
