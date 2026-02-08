## Mandatory Verification Commands

python -m compileall src
pytest tests/test_traceability.py
pytest tests/test_execution_intent_modes.py
pytest tests/test_sqlite_persistence.py
pytest tests/test_replay_from_storage_epoch4.py