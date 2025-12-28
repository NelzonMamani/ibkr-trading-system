PHASE_8_STEP_8_6_CODEX_INSTRUCTIONS_EVENT_TIME_INDEXING.md
PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.6 — EVENT TIME INDEXING & RANGE QUERIES
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.6 — EVENT TIME INDEXING & RANGE QUERIES

You are Codex operating on the IBKR Trading System repository.

Your task is to extend the RunEventTimeline with **time-based querying**
capabilities. This allows inspection of events within precise temporal
boundaries, which is essential for diagnostics, replay analysis, and audits.

This step builds directly on:
- Step 8.4 (aggregation APIs)
- Step 8.5 (filtering APIs)

---

## OBJECTIVE

You will introduce **time-range indexing helpers** that allow callers to:

- Retrieve events after a given timestamp
- Retrieve events before a given timestamp
- Retrieve events between two timestamps (inclusive)

These APIs must be read-only and deterministic.

---

## FILES TO MODIFY

You must modify **only** the following file:

- `src/core/run_event_timeline.py`

Do not modify any other files.

---

## STEP 1 — EVENTS AFTER TIMESTAMP

Inside `RunEventTimeline`, add:

```python
from datetime import datetime

def events_after(self, timestamp: datetime) -> list:
    return [
        event for event in self._events
        if event.timestamp >= timestamp
    ]

STEP 2 — EVENTS BEFORE TIMESTAMP

Add the inverse query:

def events_before(self, timestamp: datetime) -> list:
    return [
        event for event in self._events
        if event.timestamp <= timestamp
    ]

STEP 3 — EVENTS BETWEEN TIMESTAMPS

Add a bounded-range query:

def events_between(self, start: datetime, end: datetime) -> list:
    return [
        event for event in self._events
        if start <= event.timestamp <= end
    ]

STEP 4 — SAFETY & STYLE RULES

Ensure the following invariants:

No mutation of _events

No sorting or reordering

Preserve original insertion order

No logging or printing

Assume timestamps are timezone-consistent (no conversion)

VALIDATION REQUIREMENTS

After implementation:

Time-based queries return correct subsets

Existing filtering and aggregation APIs still work

Replay logic remains untouched

System runtime output is unchanged unless APIs are explicitly used

COMPLETION CRITERIA

This step is complete when:

Time-based queries function correctly

Timeline remains deterministic

No regressions appear in Phase 8 or earlier

System boots and runs normally

Do not proceed until this step is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. Copy the **entire block above**
2. Paste into **Codex**
3. Let Codex implement it
4. Run once to confirm no behaviour changes

When done, reply **exactly** with:

> **“STEP 8.6 complete — ready for Phase 8 Step 8.7”**

You are now within **audit-grade observability** territory.
