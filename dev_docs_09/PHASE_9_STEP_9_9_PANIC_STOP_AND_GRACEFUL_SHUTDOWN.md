# PHASE_9_STEP_9_9_PANIC_STOP_AND_GRACEFUL_SHUTDOWN.md

## Goal (Phase 9 · Step 9.9)
Add a **Panic Stop / Kill Switch** and a **graceful shutdown protocol** that works consistently across SIM / PAPER / LIVE, integrates with the Phase 9 runtime safety gates (9.7) and fault classification boundaries (9.8), and ensures the system can stop safely at any time without leaving “dangling” state.

This step is teaching-first but must be structurally correct for later broker integration.

---

## Non-Goals (explicit)
- No real broker cancels/flattening (still skeleton).
- No external process supervisor.
- No complex persistence system (StorageEngine remains placeholder).

---

## Design Requirements

### R1 — Single source of truth for “stop requested”
Introduce a central stop token / stop controller that can be queried by:
- Orchestrator run loop
- Any engine stage (scanner/pattern/strategy/risk/execution/exit/storage)
- Fault recovery logic (9.8)

**Stop state must be idempotent**:
- Calling `request_stop()` multiple times is safe.
- Calling `is_stop_requested()` is cheap.

### R2 — Panic stop vs graceful stop
Provide two stop modes:
1) **GRACEFUL stop**  
   - Finish current cycle safely where possible.
   - Run “shutdown hooks”.
   - Emit events describing shutdown.
2) **PANIC stop**  
   - Exit immediately from loop and skip non-essential work.
   - Still emit a minimal shutdown event record (best effort).
   - Never attempt “extra” actions that could cause instability.

### R3 — Recovery integration (9.8)
Phase 9.8 outputs a `RecoveryAction`. Map recovery actions to stop behaviour:
- `HALT_SYSTEM`  -> PANIC stop (default in LIVE), or GRACEFUL stop (SIM/PAPER) depending on policy.
- `SKIP_CYCLE`   -> do not stop; just skip and continue.
- `DEGRADE_MODE` -> set an internal flag (teaching-only) and continue, but allow stop request anytime.

If 9.8 currently represents actions differently, adapt accordingly, but keep the mapping above.

### R4 — Safe shutdown hooks
Define a small “shutdown sequence” with explicit hook points (even if placeholder):
- Close/release resources (placeholder print/log)
- Emit final event summary
- Snapshot state (optional placeholder)
- Confirm registry state (e.g., active trades count)

The shutdown sequence must NOT raise unhandled exceptions. If a hook fails, classify as a fault (9.8) and continue shutdown.

### R5 — Signals and KeyboardInterrupt
System must handle:
- `KeyboardInterrupt` (Ctrl+C)
- OS signals where applicable (SIGTERM, SIGINT) on supported platforms

On Ctrl+C:
- First Ctrl+C should request **GRACEFUL stop**.
- If Ctrl+C occurs again while stopping, escalate to **PANIC stop**.

(If platform differences make signals tricky, implement Ctrl+C path and a best-effort signal handler.)

---

## Implementation Tasks

### T1 — Add StopController (new module)
Create:

- `src/core/stop_controller.py`

Define:

- `class StopMode(Enum): GRACEFUL, PANIC`
- `class StopController:`
  - `request_stop(mode: StopMode, reason: str, source: str) -> None`
  - `is_stop_requested() -> bool`
  - `stop_mode() -> StopMode | None`
  - `stop_reason() -> str | None`
  - `stop_source() -> str | None`
  - Must be thread-safe enough for future (use `threading.Lock`).
  - Must be safe if called from exception blocks.

### T2 — Define Shutdown events (extend fault/event system)
Use the existing event system (SystemEvent / EventCollector) and add event types:
- `SHUTDOWN_REQUESTED`
- `SHUTDOWN_STARTED`
- `SHUTDOWN_HOOK_FAILED`
- `SHUTDOWN_COMPLETE`
- `PANIC_STOP_TRIGGERED`

Where to place event typing depends on your current structure. Keep it consistent with Phase 8/9 events.

Payload must include:
- mode: GRACEFUL/PANIC
- reason
- source
- run_mode
- tick
- timestamp (already present)

### T3 — Integrate StopController into CoreOrchestrator
Modify:

- `src/core/orchestrator.py`

Required changes:
1) Orchestrator owns a `StopController` instance:
   - `self.stop_controller = StopController()`

2) Continuous loop checks stop state:
   - If stop requested before starting a new cycle:
     - execute shutdown sequence
     - break loop

3) During a cycle (`run_once`), check stop state at safe boundaries:
   - After scanner
   - After pattern
   - After strategy
   - After risk
   - After execution
   - After trade exit
   - Before storage

If stop requested:
- In GRACEFUL: stop after completing the current stage boundary.
- In PANIC: exit stage immediately (best effort) and return.

4) KeyboardInterrupt handling:
   - In `run_forever()` (or equivalent):
     - first Ctrl+C => `request_stop(GRACEFUL, reason="KeyboardInterrupt", source="Main")`
     - second Ctrl+C while stop already requested => `request_stop(PANIC, reason="KeyboardInterrupt (escalation)", source="Main")`

### T4 — Add Shutdown Sequence method
In orchestrator:

- `_shutdown(mode: StopMode) -> None`

Flow:
- Emit `SHUTDOWN_STARTED`
- Run shutdown hooks in order (each in try/except):
  1) `ExecutionEngine.shutdown()` (add method if missing; placeholder)
  2) `StorageEngine.shutdown()` (placeholder)
  3) `EventCollector.flush_summary()` (or a placeholder summary method)
  4) `TradeRegistry.verify_empty()` (if present; else log current active count)
- If a hook fails:
  - Emit `SHUTDOWN_HOOK_FAILED` with exception info (string)
  - Classify the exception using 9.8 fault classifier (best effort)
  - Continue shutdown (do not re-raise)
- Emit `SHUTDOWN_COMPLETE`

In PANIC mode:
- Skip non-essential hooks (storage flush, summaries) and perform only minimal safe actions + emit PANIC stop event.

### T5 — Engine shutdown placeholders
Add `shutdown()` method stubs (idempotent) to:
- `src/engines/execution_engine.py`
- `src/engines/storage_engine.py`
- `src/engines/trade_exit_engine.py` (if exists)
- Any other engine that holds resources

These should not do much right now, but must exist for structure and future integration.

### T6 — Tests (minimum)
Create:

- `tests/test_stop_controller.py`
- `tests/test_orchestrator_shutdown.py`

Test cases:
1) StopController is idempotent; second request keeps strongest mode (PANIC overrides GRACEFUL).
2) Orchestrator loop exits when stop requested before next cycle.
3) Ctrl+C escalation behaviour (simulate by calling the handler logic directly if needed).
4) Shutdown hooks do not raise unhandled exceptions even when a hook raises.

If a full orchestrator loop test is complex, test `_shutdown()` directly with mocked engines.

---

## Acceptance Criteria
- Running `python -m src.main` still works and logs boot + cycles.
- Ctrl+C triggers a GRACEFUL shutdown sequence with events.
- A second Ctrl+C escalates to PANIC stop.
- Shutdown hooks run without crashing; failures are captured as events.
- Stop requests can be initiated from:
  - manual call (future UI)
  - fault recovery action mapping (9.8)
  - KeyboardInterrupt
- Tests pass.

---

## Notes / Teaching Intent
Explain in code comments:
- Why stop state is centralised
- Why PANIC vs GRACEFUL exists
- Why shutdown hooks must be idempotent
- How this prepares for real broker cancel/flatten logic later

---

## Deliverables (commit)
- New: `src/core/stop_controller.py`
- Updated: `src/core/orchestrator.py`
- Updated: engine modules to add `shutdown()`
- New tests: `tests/test_stop_controller.py`, `tests/test_orchestrator_shutdown.py`
- Any small refactors needed to keep imports clean and avoid circular imports
