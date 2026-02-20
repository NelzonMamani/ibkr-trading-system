# 05 — Acceptance Criteria

E24 is accepted when all are true:

1. **No event-loop RuntimeError**
   - `pytest -q` completes collection and runs tests without `RuntimeError: There is no current event loop...`.

2. **Import-time safety**
   - importing the following does not crash:
     - `src.scanner.providers.factory`
     - `src.ibkr.market_data_client` (or is safely deferred/guarded)
     - `src.core_engine.orchestrator`

3. **Deterministic runtime helper exists**
   - A canonical helper exists (recommended: `src/runtime/async_runtime.py`) providing:
     - `ensure_event_loop()` (idempotent)
     - `run(coro)` or equivalent optional helper
   - This helper is used by entrypoints/tests where needed.

4. **Evidence produced**
   - `AUDIT_EVIDENCE/e24_async_runtime_report.json`
   - `AUDIT_EVIDENCE/e24_async_import_chain_map.json`

5. **No regressions**
   - Existing governance locks, run-mode semantics, and execution gating remain intact.

