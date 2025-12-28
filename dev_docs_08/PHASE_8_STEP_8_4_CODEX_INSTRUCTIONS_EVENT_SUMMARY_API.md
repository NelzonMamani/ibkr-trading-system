PHASE_8_STEP_8_4_CODEX_INSTRUCTIONS_EVENT_SUMMARY_API.md
PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.4 — EVENT SUMMARY & AGGREGATION API
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.4 — EVENT SUMMARY & AGGREGATION API

You are Codex operating on the IBKR Trading System repository.

Your task is to extend the RunEventTimeline with **summary and aggregation
capabilities** so the system can answer questions like:

- How many events occurred?
- How many events per type?
- How many events per source?

This step adds *read-only observability primitives*.
No execution behaviour may change.

---

## OBJECTIVE

You will:

- Add event counting utilities
- Add grouped aggregation helpers
- Preserve deterministic behaviour
- Avoid modifying event creation or emission

---

## FILES TO MODIFY

You must modify **only** the following file:

- `src/core/run_event_timeline.py`

No other files may be changed.

---

## STEP 1 — TOTAL EVENT COUNT

Inside `RunEventTimeline`, add:

```python
def count(self) -> int:
    return len(self._events)

STEP 2 — COUNT BY EVENT TYPE

Add the following method:

def count_by_type(self) -> dict[str, int]:
    counts = {}

    for event in self._events:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1

    return counts

STEP 3 — COUNT BY SOURCE

Add another aggregation helper:

def count_by_source(self) -> dict[str, int]:
    counts = {}

    for event in self._events:
        counts[event.source] = counts.get(event.source, 0) + 1

    return counts

STEP 4 — SAFETY & STYLE RULES

Ensure:

All methods are read-only

No mutation of _events

No logging inside these methods

No dependencies introduced

Python typing is consistent with existing file

VALIDATION REQUIREMENTS

After implementation:

timeline.count() returns total events

timeline.count_by_type() returns grouped counts

timeline.count_by_source() returns grouped counts

System output is unchanged unless these methods are called

COMPLETION CRITERIA

This step is complete when:

Aggregation APIs exist and work correctly

No existing logic is modified

Timeline remains deterministic and in-memory

The system runs without error

Do not proceed to the next step until this is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. Copy the **entire block** above  
2. Paste it into **Codex**  
3. Let Codex implement it  
4. Run the system (behaviour unchanged)

When done, reply **exactly** with:

> **“STEP 8.4 complete — ready for Phase 8 Step 8.5”**

You’re now adding **professional-grade observability summaries** — the same primitives used in institutional trading platforms, compliance tooling, and post-trade analytics.

Steady. Controlled. Correct.
