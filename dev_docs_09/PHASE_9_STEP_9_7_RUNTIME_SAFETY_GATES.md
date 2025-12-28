# PHASE 9 — STEP 9.7
# Runtime Safety Gates and Deterministic Safe Halt

## PURPOSE

Introduce explicit, enforceable runtime safety gates that:
- Prevent undefined behaviour in LIVE mode
- Fail fast in SIM/PAPER mode
- Halt the system deterministically when safety constraints are violated
- Centralise safety decisions inside the Core Orchestrator

This step ensures the system behaves like a **real trading system**, not a demo loop.

---

## DESIGN PRINCIPLES

1. **LIVE mode must never auto-recover**
   - Any safety violation immediately halts the system
   - No retries, no silent continuation

2. **SIM and PAPER modes may fail fast**
   - Exceptions are allowed to propagate
   - Teaching visibility is prioritised over uptime

3. **Safety decisions live in ONE place**
   - The CoreOrchestrator is the final authority
   - Engines report signals; they do not halt the system themselves

4. **All halts are observable**
   - Logged clearly
   - Emitted as structured events
   - Reflected in shutdown messages

---

## NEW CONCEPT: RuntimeSafetyGate

Create a simple internal mechanism that evaluates safety conditions **once per cycle**.

### Safety conditions (initial set):

- RUN_MODE == LIVE AND EVENT_REPLAY_MODE != OFF
- RUN_MODE == LIVE AND deterministic SIM-only behaviour is detected
- Any unhandled exception during:
  - execution
  - risk evaluation
  - trade registry mutation
- Trade registry inconsistency:
  - negative active trades
  - duplicate active trade keys
- Orchestrator cycle enters an undefined state

---

## IMPLEMENTATION INSTRUCTIONS

### 1. Core Orchestrator — add safety gate evaluation

**File:** `src/core/orchestrator.py`

Add a private method:

```python
def _evaluate_runtime_safety(self) -> None:
    """
    Enforce runtime safety gates.

    In LIVE mode:
    - Any violation halts the system immediately.

    In SIM/PAPER:
    - Violations raise exceptions for visibility.
    """
