PHASE_9_STEP_9_8_FAULT_CLASSIFICATION_AND_RECOVERY_BOUNDARIES.md
# PHASE 9 — STEP 9.8
# Fault Classification and Recovery Boundaries

## PURPOSE

Introduce a formal, explicit fault taxonomy that classifies runtime failures into
well-defined categories and defines *deterministic recovery boundaries*.

This step ensures:
- Failures are **classified before any recovery decision**
- LIVE mode is **strictly conservative**
- SIM/PAPER may recover more aggressively but still auditable
- A single place defines what is **recoverable vs fatal**

This prevents accidental “auto-healing” behaviour in LIVE mode and makes failure
behaviour predictable, testable, and reviewable.

---

## SCOPE

This step adds:
1. A `FaultCategory` enum and `FaultSeverity` / `RecoveryAction` primitives
2. A `FaultEvent` dataclass (structured failure payload)
3. A classifier function (exception → fault category)
4. A recovery policy function (fault category + run_mode → recovery action)
5. A small orchestrator integration point that:
   - classifies
   - emits a system event
   - applies policy
   - halts safely when required

No external APIs. No broker calls. Teaching-first.

---

## DEFINITIONS

### FaultCategory (what happened)
A stable label that describes *the nature* of the failure:
- CONFIG
- SAFETY
- IO
- DATA
- EXTERNAL
- LOGIC
- STATE
- UNKNOWN

### FaultSeverity (how bad)
A normalized severity:
- INFO (not a fault; informational)
- WARNING (recoverable)
- ERROR (recoverable but serious)
- CRITICAL (must halt or escalate)

### RecoveryAction (what to do)
- IGNORE (record only, continue)
- RETRY (repeat the failing unit of work with controlled bounds)
- SKIP_STAGE (skip a stage for this cycle)
- ABORT_CYCLE (end the current cycle safely)
- HALT_SYSTEM (stop the main loop; require operator intervention)

---

## RECOVERY BOUNDARIES (POLICY MATRIX)

### LIVE (strict)
LIVE must never “power through” unclear failures.

| Category   | Default Action | Notes |
|-----------|----------------|------|
| SAFETY    | HALT_SYSTEM    | Any safety violation halts immediately |
| CONFIG    | HALT_SYSTEM    | Misconfig is operator error |
| STATE     | HALT_SYSTEM    | State inconsistency is too risky |
| LOGIC     | HALT_SYSTEM    | Programming logic error must halt |
| IO        | ABORT_CYCLE    | Abort cycle; do not attempt noisy recovery |
| DATA      | SKIP_STAGE     | Missing/invalid data may skip, still log |
| EXTERNAL  | ABORT_CYCLE    | Abort cycle; never infinite retry in LIVE |
| UNKNOWN   | HALT_SYSTEM    | Unknown = unsafe |

### PAPER (moderate)
PAPER behaves more like LIVE than SIM but allows *bounded retries*.

| Category   | Default Action |
|-----------|----------------|
| SAFETY    | HALT_SYSTEM |
| CONFIG    | HALT_SYSTEM |
| STATE     | HALT_SYSTEM |
| LOGIC     | HALT_SYSTEM |
| IO        | RETRY (bounded), else ABORT_CYCLE |
| DATA      | SKIP_STAGE |
| EXTERNAL  | RETRY (bounded), else ABORT_CYCLE |
| UNKNOWN   | ABORT_CYCLE (or HALT if repeated) |

### SIM (permissive but observable)
SIM may continue more often to keep teaching flows running, but must still record faults.

| Category   | Default Action |
|-----------|----------------|
| SAFETY    | HALT_SYSTEM (still) |
| CONFIG    | ABORT_CYCLE |
| STATE     | ABORT_CYCLE |
| LOGIC     | ABORT_CYCLE |
| IO        | RETRY (bounded), else SKIP_STAGE |
| DATA      | SKIP_STAGE |
| EXTERNAL  | RETRY (bounded), else ABORT_CYCLE |
| UNKNOWN   | ABORT_CYCLE |

---

## IMPLEMENTATION PLAN

### A) Add new module: `src/core/faults.py`

Create:
- `FaultCategory` enum
- `FaultSeverity` enum
- `RecoveryAction` enum
- `FaultEvent` dataclass
- `classify_exception(exc: Exception) -> FaultEvent`
- `decide_recovery_action(fault: FaultEvent, run_mode: RunMode) -> RecoveryAction`

Also include:
- A small helper `fault_to_payload(fault) -> dict` to emit in SystemEvent payloads.

**Classifier guidance** (simple heuristics are fine for now):
- `ValueError`, `TypeError` often → DATA or LOGIC depending on context
- `KeyError` often → DATA
- `FileNotFoundError`, `OSError` → IO
- `RuntimeError` raised by safety gates → SAFETY
- Anything else → UNKNOWN

We prefer explicit mapping over clever inference.
Start conservative: anything unclear becomes UNKNOWN.

### B) Integrate into orchestrator: `src/core/orchestrator.py`

Add:
- a wrapper around `run_once()` internals or around each stage that catches exceptions,
  calls the classifier, emits an event, then applies policy.

Minimum viable integration:
- Wrap the entire `run_once()` body in try/except.
- On exception:
  1. `fault = classify_exception(exc)`
  2. emit `SystemEvent(event_type="FAULT_DETECTED", source="Orchestrator", payload=...)`
  3. `action = decide_recovery_action(fault, self.run_mode)`
  4. apply the action:
     - IGNORE → continue
     - RETRY → (for this step, do NOT implement full retry loops; just map to ABORT_CYCLE unless already implemented)
     - SKIP_STAGE → (if whole-run wrapper, treat as ABORT_CYCLE for now)
     - ABORT_CYCLE → return safely
     - HALT_SYSTEM → raise `SystemExit` or set a `self._halt_requested` flag that main loop respects

**Important:** no infinite loops. No unbounded retry.

### C) Add new event types
Add (no need for a new module if events are string-based already):
- `FAULT_DETECTED`
- `FAULT_ACTION_TAKEN`

If you have an event registry / constants file, add them there; otherwise keep as strings.

### D) Add tests: `tests/test_faults.py` (or `src/tests/...` depending on your structure)

At minimum:
1. `FileNotFoundError` → category IO
2. `KeyError` → category DATA
3. `RuntimeError` with message containing `[SAFETY]` or `[REPLAY]` → SAFETY
4. For LIVE run_mode:
   - SAFETY → HALT_SYSTEM
   - UNKNOWN → HALT_SYSTEM
   - DATA → SKIP_STAGE or ABORT_CYCLE (whatever policy you encoded)

---

## CODING STANDARD RULES

- Do not add new dependencies.
- Keep functions pure and deterministic.
- Keep all policies centralized in `faults.py`.
- Orchestrator must not “invent” policy rules locally.
- Emit structured payloads: category, severity, message, exception type, run_mode, recommended_action.
- Ensure that failures are visible in logs and events.

---

## RECOMMENDED FILE CONTENTS (REFERENCE SHAPE)

### `src/core/faults.py` should contain:

- Enums:
  - `FaultCategory`
  - `FaultSeverity`
  - `RecoveryAction`

- Dataclass:
  - `FaultEvent(category, severity, message, exception_type, stack_hint=None, timestamp=None)`

- Functions:
  - `classify_exception(exc: Exception) -> FaultEvent`
  - `decide_recovery_action(fault: FaultEvent, run_mode: RunMode) -> RecoveryAction`
  - `fault_to_payload(fault: FaultEvent, run_mode: RunMode, action: RecoveryAction) -> dict`

---

## ACCEPTANCE CRITERIA

Step 9.8 is complete when:

1. A new `faults.py` exists and exposes classification + policy decision.
2. Orchestrator catches failures and emits `FAULT_DETECTED`.
3. Orchestrator applies recovery actions deterministically:
   - LIVE: SAFETY/UNKNOWN must halt
   - LIVE: CONFIG/STATE/LOGIC must halt
4. Tests exist and pass for the core classifier + policy matrix.
5. Running `main.py` still works exactly as before in the happy-path.

---

## OUT OF SCOPE (NOT IN 9.8)

- Per-stage retry loops with exponential backoff
- Persistent fault journaling to disk
- Broker connectivity failure policies
- Circuit breaker patterns
- Alerting/notifications

Those can come later once structure is stable.

---

## NOTES (TEACHING-FIRST)

Keep classification + policy simple and readable. The goal is to make runtime
behaviour *predictable*, not sophisticated.

“Unknown means unsafe” is a deliberate safety stance in LIVE mode.


If you want, I can also provide the exact Codex instruction block to implement Step 9.8 (Option B — Direct) in one paste, like we’ve been doing for Phase 9.

is this not direct? is this block of instructions not complete for 9.8 ? 

Yes — this is direct, and yes — it is complete for PHASE 9 · STEP 9.8.
You were right to question it, so let me be very explicit and remove all doubt.

✅ Short, precise answer

Yes.
The Markdown block I gave you is a fully valid, complete, single-copy-paste Codex instruction file for:

PHASE_9_STEP_9_8_FAULT_CLASSIFICATION_AND_RECOVERY_BOUNDARIES.md

You can paste that entire block as-is into Codex and it has everything Codex needs to implement Step 9.8 correctly.