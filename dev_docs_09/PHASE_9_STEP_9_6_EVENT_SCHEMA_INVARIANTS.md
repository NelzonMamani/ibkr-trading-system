📄 FILE: PHASE_9_STEP_9_6_EVENT_SCHEMA_INVARIANTS.md
# PHASE 9 — STEP 9.6
# Event Schema Invariants (Audit-Grade, Teaching-First)

## OBJECTIVE
Lock down event integrity by adding lightweight schema validation + invariants so:
- event payloads are consistent (especially trade lifecycle)
- replay is deterministic and safe
- future phases can rely on event contracts without fragile coupling

This is NOT heavy validation or external libraries.
Keep it teaching-first and minimal.

---

## REQUIRED CHANGES

### 1) Create minimal event schema definitions
New file:
src/events/event_schema.py

Add:
- EventSchemaError(Exception)
- REQUIRED_FIELDS dict keyed by event_type -> set[str]
- OPTIONAL_FIELDS dict keyed by event_type -> set[str] (optional)

At minimum define schemas for these event types (exact names must match your system):
- CYCLE_START
- SCAN_COMPLETE
- STRATEGY_COMPLETE
- EXECUTION_COMPLETE
- TRADE_OPENED
- TRADE_CLOSED
- TRADE_EXIT_COMPLETE
- STRATEGY_PERF_SNAPSHOT  (from Step 9.5)

Example required fields (adjust to match your payloads, but enforce consistency):
- CYCLE_START: {"run_mode"}
- SCAN_COMPLETE: {"candidates"}
- STRATEGY_COMPLETE: {"trade_intents"}
- EXECUTION_COMPLETE: {"results"}

Trade lifecycle (most important):
- TRADE_OPENED: {"symbol","trader_type","strategy_name","entry_price","entry_tick"}
- TRADE_CLOSED: {"symbol","trader_type","strategy_name","entry_price","exit_price","pnl","entry_tick","exit_tick"}
- TRADE_EXIT_COMPLETE: {"closed"} (and optionally list of closed symbols/results if you already include it)

Strategy perf snapshot:
- STRATEGY_PERF_SNAPSHOT: {"strategies"}

Make the required fields conservative: enforce only what you truly need.

---

### 2) Add a validator function
In the same file implement:

def validate_event(event_type: str, payload: dict) -> None:
    - ensure payload is dict
    - ensure all REQUIRED_FIELDS[event_type] exist
    - if OPTIONAL_FIELDS exists, allow them
    - allow extra keys (teaching-friendly) BUT print a debug note once per unknown key group:
      "[SCHEMA] event=<type> has extra keys: ..."

If event_type unknown:
- allow it (do not crash), but log:
  "[SCHEMA] Unknown event_type=<type> (no schema registered)"

If required fields missing:
- raise EventSchemaError with a clear message listing missing keys

---

### 3) Enforce validation at the single source of truth: EventCollector.emit()
Find your EventCollector (or whichever class creates SystemEvent).
Modify emit so it calls validate_event(event_type, payload) before creating the event.

Important:
- validation must happen at the moment the event is created/emitted, not later.

---

### 4) Add invariants checks for trade lifecycle sequencing
New file:
src/events/event_invariants.py

Implement a small in-memory checker:

class EventInvariantError(Exception)

class TradeLifecycleInvariantChecker:
  - tracks opened positions by (symbol, trader_type)
  - on TRADE_OPENED: assert not already open
  - on TRADE_CLOSED: assert was open, then remove
  - if violation: raise EventInvariantError with explanation

Also provide:
def check_invariants(events: list[SystemEvent]) -> None
- iterate in order and apply the checker
- only checks TRADE_OPENED / TRADE_CLOSED for now

Where to use:
- In replay: run check_invariants(replayed_events) at end and print:
  "[REPLAY][INVARIANTS] OK" or a clear failure message
- In live run: after each cycle, check invariants on current cycle events only
  (so one bad cycle is detected quickly)

Safety:
- In LIVE mode, do NOT crash the full run loop on invariant failure.
  Instead:
  - log "[INVARIANTS] VIOLATION — entering safe halt"
  - break the loop / stop orchestrator cleanly

In SIM mode:
- can raise to fail fast (teaching benefit)

---

### 5) Make the invariants visible in logs
At end of cycle:
- if OK: "[INVARIANTS] OK"
- if failure: "[INVARIANTS] FAILED: <reason>"

At replay:
- always show the invariant result

---

## SAFETY CONSTRAINTS
- no new dependencies
- no external schema libraries
- do not change trading logic
- do not change event type names
- do not remove existing payload fields

---

## ACCEPTANCE CHECKS
1) Run main.py:
- Should still run normally.
- You should see:
  - schema validation silently passing
  - "[INVARIANTS] OK" per cycle

2) Intentionally break a payload (remove a required field) and confirm:
- EventSchemaError raised with missing keys (in SIM)
- In LIVE, system halts safely with a clear log

3) Replay should show:
- "[REPLAY][INVARIANTS] OK"

Report back exactly:
"STEP 9.6 complete — ready for Phase 9 Step 9.7"


When you reply “STEP 9.6 complete”, we’ll do Step 9.7, which typically tightens config + runtime safety gates to ensure Phase 10 can plug in real adapters without risk.
