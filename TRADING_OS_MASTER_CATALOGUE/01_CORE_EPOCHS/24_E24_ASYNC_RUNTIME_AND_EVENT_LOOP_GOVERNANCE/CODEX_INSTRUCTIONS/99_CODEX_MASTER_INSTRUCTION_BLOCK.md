# 99 — CODEX MASTER INSTRUCTION BLOCK (COPY/PASTE)

FILE: TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/24_E24_ASYNC_RUNTIME_AND_EVENT_LOOP_GOVERNANCE/CODEX_INSTRUCTIONS/99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: E24 ASYNC RUNTIME & EVENT LOOP GOVERNANCE — IMPLEMENTATION MASTER INSTRUCTIONS

You are Codex operating in repo: `ibkr-trading-system`.

OBJECTIVE:
Restore Python 3.14+ runtime compatibility by eliminating import-time event-loop failures (notably eventkit/ib_insync) and making event loop ownership deterministic.
This is a Core Epoch: E24 Async Runtime & Event Loop Governance.

NON-NEGOTIABLES:
- Additive/minimal changes only. No redesign. No epoch renames.
- Pytest must not fail at collection due to missing event loop.
- Imports must be safe in SIM/PAPER/READ_ONLY without IBKR connectivity.
- Produce evidence JSON under `AUDIT_EVIDENCE/`.

TASKS (DO IN ORDER):
1) Create canonical runtime helper:
   - Create/update `src/runtime/async_runtime.py` with `ensure_event_loop()` that is idempotent and Python 3.14-safe.
2) Fix import chain:
   - Choose minimal approach:
     A) Defer `ib_insync` imports inside runtime functions, OR
     B) Create `src/ibkr/ib_insync_compat.py` that calls `ensure_event_loop()` then imports ib_insync, and switch IBKR modules to import via this wrapper.
3) If still needed for pytest collection, add minimal `tests/conftest.py` hook that calls `ensure_event_loop()` once (no IBKR connections).
4) Add evidence script:
   - `verification_scripts/e24_async_runtime_restoration.py`
   - It must write:
     - `AUDIT_EVIDENCE/e24_async_runtime_report.json`
     - `AUDIT_EVIDENCE/e24_async_import_chain_map.json`
5) Update certification:
   - Update `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` to record E24 and evidence paths.

MANDATORY VERIFICATION (MUST RUN AND INCLUDE OUTPUT/EVIDENCE):
- `python -m compileall src`
- `python verification_scripts/e24_async_runtime_restoration.py`
- `pytest -q`

SUCCESS CRITERIA:
- `pytest -q` completes with zero collection errors and no event-loop RuntimeError.
- Evidence JSON files exist and are non-empty.
- No regressions to run modes/execution gating.

STOP CONDITION:
Stop after verification passes and evidence + certification updates are committed.

END
