# 02 — Implementation Tasks (Additive Fixes Only)

## Task 1 — Add canonical runtime helper
Create (or update if exists):
- `src/runtime/async_runtime.py`

Required API:
- `ensure_event_loop() -> asyncio.AbstractEventLoop`
  - idempotent
  - creates loop and sets it for current thread if missing
  - must be safe on Python 3.14
  - should handle Windows policy safely (only if required; do not overreach)

Optional API:
- `run(coro)` or `run_sync(coro)` helper for controlled async execution

## Task 2 — Guard third-party import chains
Goal: importing modules must not crash during pytest collection.

Preferred minimal options (choose one, smallest change):
A) **Defer ib_insync imports**
- Move `from ib_insync import ...` imports inside functions/methods that execute only at runtime, not at import.
- Ensure those call sites have already called `ensure_event_loop()`.

B) **Local guarded import wrapper**
- Create a small wrapper module, e.g. `src/ibkr/ib_insync_compat.py`
- In it, call `ensure_event_loop()` then import `ib_insync`.
- All IBKR modules import through the wrapper.

Do not mix A and B unless necessary.

## Task 3 — Test harness / conftest safety (minimal)
If tests import modules that indirectly trigger the chain, add a minimal pytest safety hook:
- `tests/conftest.py` (only if not already present and only if needed)
- call `ensure_event_loop()` early **without** connecting to IBKR

## Task 4 — Evidence script
Add `verification_scripts/e24_async_runtime_restoration.py` that:
- prints python version/platform
- calls `ensure_event_loop()` and reports actions taken
- imports the sensitive modules (scanner provider factory, market data client) to prove import safety
- optionally runs `pytest -q` via subprocess (or just instruct operator to run)

Script must write:
- `AUDIT_EVIDENCE/e24_async_runtime_report.json`
- `AUDIT_EVIDENCE/e24_async_import_chain_map.json`

## Task 5 — Certification updates
Update:
- `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md`
and/or the appropriate integrity/certification index files to record:
- E24 exists
- status: VERIFIED/CERTIFIED (only after `pytest -q` passes)
- evidence paths

