# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.2 — EVENT COLLECTOR (IN-MEMORY, TEACHING-FIRST)

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce a **central EventCollector**
that records all emitted SystemEvents during runtime.

This collector is NOT async.
This collector is NOT persistent.
This collector is the foundation for:
- Auditing
- Replay
- Metrics
- Debugging

---

## GLOBAL OBJECTIVE

You will:

- Create an in-memory EventCollector
- Register events during runtime
- Preserve synchronous execution
- Maintain deterministic behavior
- Keep visibility via prints

---

## FILES YOU MAY MODIFY

You must modify **only** the following files:

- `src/core/event_collector.py` (NEW FILE)
- `src/core/orchestrator.py`

Do NOT modify any other files.

---

## STEP 1 — CREATE EVENT COLLECTOR

Create a new file:

📄 `src/core/event_collector.py`

Add the following code:

```python
class EventCollector:
    """
    In-memory collector for SystemEvents.
    Teaching-first, synchronous, deterministic.
    """

    def __init__(self):
        self._events = []

    def record(self, event):
        print(f"[EVENT_COLLECTOR] Recording event: {event.event_type}")
        self._events.append(event)

    def snapshot(self):
        return list(self._events)

    def count(self):
        return len(self._events)
```

---

## STEP 2 — CONNECT COLLECTOR TO ORCHESTRATOR

Modify:

📄 `src/core/orchestrator.py`

### A) Import the collector

At the top of the file, add:

```python
from core.event_collector import EventCollector
```

---

### B) Instantiate collector in Orchestrator

Inside `Orchestrator.__init__()`:

```python
self.event_collector = EventCollector()
```

Add a print:

```python
print("[BOOT] EventCollector initialised")
```

---

### C) Record events after each emission

Immediately after **each** `print(SystemEvent(...))` call,
add the following line:

```python
self.event_collector.record(event)
```

⚠️ This requires you to slightly refactor each emission to:

```python
event = SystemEvent(...)
print(event)
self.event_collector.record(event)
```

Apply this pattern consistently for:
- CYCLE_START
- SCAN_COMPLETE
- STRATEGY_COMPLETE
- EXECUTION_COMPLETE

---

## VALIDATION REQUIREMENTS

After implementation:

- Events are printed AND recorded
- EventCollector count increases each cycle
- Order is preserved
- No logic changes occur
- System remains deterministic

---

## COMPLETION CRITERIA

This step is complete when:

- EventCollector stores events
- Logs show recording confirmation
- Snapshot() returns all events in order

---

## ✅ NEXT ACTION

1. Copy this entire file
2. Paste into Codex
3. Run the system
4. Confirm `[EVENT_COLLECTOR] Recording event:` logs appear

When complete, reply:

> **“STEP 6.2 complete — events are collected”**
