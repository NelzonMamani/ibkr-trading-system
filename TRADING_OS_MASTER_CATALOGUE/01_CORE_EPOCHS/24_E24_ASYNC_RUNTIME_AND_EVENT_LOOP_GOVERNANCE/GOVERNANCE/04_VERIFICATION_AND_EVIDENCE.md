# 04 — Verification and Evidence

## Verification commands (minimum)
Run from repo root:

1. Compile-time check
```bash
python -m compileall src
```

2. Test collection + unit suite
```bash
pytest -q
```

3. Runtime bootstrap smoke (no external services required)
```bash
python -c "from src.runtime.async_runtime import ensure_event_loop; ensure_event_loop(); print('loop_ok')"
```

4. Orchestrator smoke (SIM and PAPER should not require TWS/IBG)
```bash
python -c "from src.core_engine.orchestrator import run_cycles; run_cycles(cycles=1)"
```

(If orchestrator requires flags in your repo, use the canonical smoke command already in your runbook; the key is: import does not crash.)

## Evidence Artifacts (required)
Under `AUDIT_EVIDENCE/` produce:
- `e24_async_runtime_report.json` containing:
  - python version, platform, UTC timestamp
  - event-loop policy details
  - whether loop existed pre-bootstrap
  - whether loop created/set by `ensure_event_loop`
  - pytest returncode summary (or reference to captured output)
- `e24_async_import_chain_map.json` listing known sensitive import chains (scanner/providers → ibkr_provider → ib_insync → eventkit) and whether guarded.

## Certification rule
E24 is **CERTIFIED** only if:
- `pytest -q` does not error at collection (no RuntimeError about event loop)
- all required evidence artifacts exist and are non-empty
- no forbidden fix is used

