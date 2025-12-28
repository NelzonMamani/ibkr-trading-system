PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.3 — EVENT FILTERING & QUERY INTERFACE
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.3 — EVENT FILTERING & QUERY INTERFACE

You are Codex operating on the IBKR Trading System repository.

Your task is to add **event filtering and querying capabilities** to the
RunEventTimeline, allowing consumers to retrieve subsets of events by
type, source, or symbol.

This introduces structured observability without modifying execution logic.

---

## OBJECTIVE

You will:

- Extend RunEventTimeline with query methods
- Enable filtering by event_type
- Enable filtering by source
- Preserve deterministic, teaching-first behaviour
- Avoid modifying event emission sites

---

## FILES TO MODIFY

You must modify **only** the following files:

- `src/core/run_event_timeline.py`

Do not modify any other files.

---

## STEP 1 — ADD FILTERING METHODS

Modify:

📄 `src/core/run_event_timeline.py`

Extend the class with the following methods:

```python
def filter_by_type(self, event_type: str):
    return [
        event for event in self._events
        if event.event_type == event_type
    ]


def filter_by_source(self, source: str):
    return [
        event for event in self._events
        if event.source == source
    ]

STEP 2 — ADD COMBINED QUERY METHOD

Still in RunEventTimeline, add a combined query helper:

def query(self, event_type: str = None, source: str = None):
    results = self._events

    if event_type:
        results = [
            e for e in results if e.event_type == event_type
        ]

    if source:
        results = [
            e for e in results if e.source == source
        ]

    return list(results)


This method must:

Accept either filter independently

Support combined filtering

Return a copy, not internal state

STEP 3 — MAINTAIN SAFETY & SIMPLICITY

Ensure:

No mutation of stored events occurs

No external dependencies are introduced

No replay logic is modified

Timeline remains in-memory only

VALIDATION REQUIREMENTS

After implementation:

filter_by_type("SCAN_COMPLETE") returns only scan events

filter_by_source("ExecutionEngine") returns execution events

query(event_type=..., source=...) works correctly

System behaviour remains unchanged when unused

COMPLETION CRITERIA

This step is complete when:

RunEventTimeline supports filtering and querying

No other system components are affected

Output remains deterministic

The system runs without errors

Do not proceed to the next step until this is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. **Copy the entire block above**
2. **Paste it into Codex**
3. Let Codex implement the changes
4. Run the system (no output change expected yet)

When finished, reply with:

> **“STEP 8.3 complete — ready for Phase 8 Step 8.4”**

You are now building **audit-grade observability primitives** — this is exactly how professional trading platforms evolve.
