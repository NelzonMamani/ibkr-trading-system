# 01 — Intent and Scope

## Intent
E24 establishes a **single authoritative async runtime model** for the Trading OS so that:

- **pytest collection never fails** due to missing event loops
- **imports are safe** in any context (CLI, tests, verifiers, orchestrator)
- **runtime boot is deterministic** (loop created/owned/closed in one place)
- **third-party async consumers** (notably `ib_insync` → `eventkit`) are compatible with Python 3.14+ event-loop semantics
- the system remains compliant with **mode semantics** (SIM/PAPER/READ_ONLY/LIVE) and **execution gating** invariants

## Scope
In-scope modules include (non-exhaustive):
- `src/runtime/*` (or equivalent runtime bootstrap layer)
- orchestrator / harness entrypoints importing scanner / broker adapters
- `src/ibkr/*` and any import chain pulling `ib_insync`/`eventkit`
- verification scripts and metadata verifiers that import runtime modules
- test suite import paths

## Problem Statement (observed)
On Python 3.14, `asyncio.get_event_loop()` no longer implicitly creates a loop for the main thread during import time. Third-party libraries (e.g., `eventkit`) may call event-loop getters at import, causing:

> `RuntimeError: There is no current event loop in thread 'MainThread'.`

This can break:
- tests at **collection** time
- verifiers importing IBKR modules
- orchestrator smoke tests

## Deliverable
A certified runtime governance + implementation (via CODEX bundle) that:
- makes import-time loop acquisition safe
- makes runtime boot deterministic and explicit
- provides evidence logs demonstrating correctness

