## Mandatory Verification Commands

All must pass.

1) Static
python -m compileall src

2) Tests
pytest tests/test_storage_recovery.py
pytest tests/test_storage_cli_epoch4.py

3) DB Admin smoke
python -c "from src.storage.db_admin import main; print('OK')"

4) Safe reset boot
python -m src.main --mode SIM --cycles 1

5) Guardrails
- Attempt destructive op while RUN_MODE=LIVE should refuse
- Same op in READ_ONLY should succeed (if confirmed)

Record outputs to output/verification/.