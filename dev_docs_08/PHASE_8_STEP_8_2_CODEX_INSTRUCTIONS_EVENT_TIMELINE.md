PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.2 — EVENT TIMELINE AGGREGATION (RUN-LEVEL VIEW)
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.2 — EVENT TIMELINE AGGREGATION (RUN-LEVEL VIEW)

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce a **run-level Event Timeline**, aggregating all
SystemEvents across cycles into a single ordered structure.

This provides a chronological, auditable view of system behaviour across
multiple orchestrator cycles.

---

## OBJECTIVE

You will:

- Introduce a RunEventTimeline component
- Collect events from all cycles in order
- Preserve existing cycle-scoped event behaviour
- Enable future audit, replay, and visualization layers
- Maintain teaching-first, deterministic behaviour

---

## FILES TO MODIFY

You must modify **only** the following files:

- `src/core/run_event_timeline.py` (NEW FILE)
- `src/core/orchestrator.py`
- `src/core/event_collector.py`

Do not modify any other files.

---

## STEP 1 — CREATE RUN EVENT TIMELINE

Create a new file:

📄 `src/core/run_event_timeline.py`

Add the following implementation:

```python
class RunEventTimeline:
    """
    Aggregates all SystemEvents across the entire runtime.
    Teaching-first, in-memory only.
    """

    def __init__(self):
        self._events = []

    def record(self, event):
        self._events.append(event)

    def snapshot(self):
        return list(self._events)

    def count(self) -> int:
        return len(self._events)

STEP 2 — CONNECT TIMELINE TO EVENT COLLECTOR

Modify:

📄 src/core/event_collector.py

Update the constructor to accept an optional run timeline:

def __init__(self, run_timeline=None):
    self.run_timeline = run_timeline
    self.cycle_events = []


Inside the method that records events, after adding the event to
cycle-scoped storage, also forward it to the run timeline if present:

if self.run_timeline:
    self.run_timeline.record(event)


Ensure:

Cycle-scoped behaviour remains unchanged

Run-level aggregation is additive only

STEP 3 — INITIALISE TIMELINE IN ORCHESTRATOR

Modify:

📄 src/core/orchestrator.py

Import the timeline:

from core.run_event_timeline import RunEventTimeline


Inside CoreOrchestrator.__init__, create the timeline:

self.run_event_timeline = RunEventTimeline()


Pass it into the EventCollector:

self.event_collector = EventCollector(
    run_timeline=self.run_event_timeline
)

STEP 4 — LOG RUN-LEVEL SUMMARY

At graceful shutdown (or after the run loop exits), log a summary:

print(
    f"[RUN_SUMMARY] Total events recorded across run: "
    f"{self.run_event_timeline.count()}"
)


Do not alter replay behaviour in this step.

VALIDATION REQUIREMENTS

After implementation:

Cycle event summaries still work unchanged

Run-level event count increases across cycles

No duplicate or missing events occur

Timeline remains in-memory only

System output remains deterministic

COMPLETION CRITERIA

This step is complete when:

A run-level event timeline exists

All events are aggregated across cycles

Cycle and run scopes are clearly separated

The system runs without errors

Do not proceed to the next step until this is complete and verified.


---

### 🟦 WHAT YOU DO NEXT (HUMAN INSTRUCTIONS)

1. **Copy the entire block above**
2. **Paste it directly into Codex**
3. Let Codex implement the changes
4. Run `main.py`
5. Confirm you see a final line like:


[RUN_SUMMARY] Total events recorded across run: XX


When done, tell me **exactly this**:

> **“STEP 8.2 complete — ready for Phase 8 Step 8.3”**

You are now operating at **institutional trading-system architecture level**.
