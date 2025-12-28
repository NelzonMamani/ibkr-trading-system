PHASE_8_STEP_8_7_CODEX_INSTRUCTIONS_EVENT_SERIALIZATION.md
PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.7 — EVENT SERIALIZATION (AUDIT-READY EXPORT)
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.7 — EVENT SERIALIZATION (AUDIT-READY EXPORT)

You are Codex operating on the IBKR Trading System repository.

Your task is to add **safe, deterministic event serialization**
capabilities to the RunEventTimeline.

This enables:
- Auditing
- Offline inspection
- Future persistence (without implementing storage yet)

This step is strictly READ-ONLY and must not affect runtime behaviour.

---

## OBJECTIVE

You will allow events to be exported into plain Python dictionaries
that are:
- JSON-serializable
- Order-preserving
- Explicit and audit-friendly

No file I/O is permitted in this step.

---

## FILES TO MODIFY

You must modify **only** the following file:

- `src/core/run_event_timeline.py`

Do not modify any other files.

---

## STEP 1 — SINGLE EVENT SERIALIZATION

Inside `RunEventTimeline`, add:

```python
def serialize_event(self, event) -> dict:
    return {
        "event_type": event.event_type,
        "source": event.source,
        "payload": event.payload,
        "timestamp": event.timestamp.isoformat(),
    }


Notes:

Use ISO 8601 string format for timestamps

Do not alter payload contents

Do not add derived fields

STEP 2 — FULL TIMELINE SERIALIZATION

Add a method to serialize all stored events:

def serialize_all(self) -> list:
    return [
        self.serialize_event(event)
        for event in self._events
    ]

STEP 3 — SERIALIZATION WITH FILTER SUPPORT

Add support for exporting subsets using existing APIs:

def serialize_filtered(self, events: list) -> list:
    return [
        self.serialize_event(event)
        for event in events
    ]


This allows callers to do:

serialize events by type

serialize events by source

serialize events by time range

without duplicating logic.

SAFETY RULES (MANDATORY)

Ensure that:

No mutation of events occurs

No logging or printing is added

No ordering changes occur

No assumptions are made about payload structure

Serialization is deterministic

VALIDATION REQUIREMENTS

After implementation:

serialize_all() returns a JSON-safe structure

Timestamp fields are ISO strings

Existing timeline APIs continue to function

Runtime output is unchanged unless serialization is explicitly used

COMPLETION CRITERIA

This step is complete when:

Events can be safely exported for audits

Timeline remains authoritative and deterministic

Phase 8 observability is materially enhanced

System runs exactly as before

Do not proceed until this step is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. Copy the **entire block above**
2. Paste it into **Codex**
3. Let Codex implement the changes
4. Run once to confirm no behavioural change

When finished, reply **exactly** with:

> **“STEP 8.7 complete — ready for Phase 8 Step 8.8”**

You are now building **institutional-grade traceability**, not demos.
