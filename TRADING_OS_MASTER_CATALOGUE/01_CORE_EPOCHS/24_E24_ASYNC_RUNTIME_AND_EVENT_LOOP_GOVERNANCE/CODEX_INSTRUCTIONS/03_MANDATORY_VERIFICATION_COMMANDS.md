# 03 — Mandatory Verification Commands

Run from repo root and attach outputs (or summaries) to audit evidence.

1) Compile
```bash
python -m compileall src
```

2) E24 evidence script
```bash
python verification_scripts/e24_async_runtime_restoration.py
```

3) Pytest (must pass collection)
```bash
pytest -q
```

4) Optional: smoke import checks
```bash
python -c "import src.scanner.providers.factory; import src.ibkr.market_data_client; print('import_ok')"
```

## Success criteria
- `pytest -q` has **zero collection errors**
- Evidence JSON files exist under `AUDIT_EVIDENCE/`
- No behavioural regressions to run modes / execution gating

