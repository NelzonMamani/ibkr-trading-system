# 02 — Canonical Runtime Model

## Definitions
- **Runtime bootstrap**: the earliest authoritative point where the program chooses a run mode, config, and initializes runtime services.
- **Event loop ownership**: which component is responsible for creating/setting/closing the loop.
- **Import-time safety**: importing any module must not require an event loop to exist.

## Canonical Model (Institutional)
### A) Import-time
- No module import may require a running loop.
- No module import may call loop getters that throw if unset (directly or indirectly) *unless guarded*.
- IBKR-facing modules must defer any loop-dependent initialization until runtime bootstrap.

### B) Program entry (CLI / orchestrator / harness)
- A single runtime authority creates and sets the loop for the main thread.
- Runtime authority sets policy if required (Windows policy nuances).
- Runtime authority provides helpers for:
  - `ensure_event_loop()` (idempotent)
  - `run_async(coro)` with controlled loop semantics
  - test-safe variants if needed

### C) Shutdown
- Loop is gracefully drained.
- All pending tasks are cancelled/awaited where appropriate.
- Loop is closed deterministically.

## Minimal Compatibility Approach
E24 prefers **minimal shims** rather than invasive refactors:
- central runtime helper module that can be imported everywhere
- lightweight guard executed early in entrypoints (and optionally in tests via conftest)

## Required Integration Points
- Test harness: before importing IBKR-bound modules, ensure loop exists (or block/skip if IBKR disabled)
- Scanner provider factory: must not import IBKR provider in contexts where IBKR is disabled (already partially in place); E24 ensures any remaining imports do not crash.

