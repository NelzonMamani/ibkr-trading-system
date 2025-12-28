PHASE_8_STEP_8_5_CODEX_INSTRUCTIONS_EVENT_FILTERING_API.md
PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.5 — EVENT FILTERING & QUERY API
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.5 — EVENT FILTERING & QUERY API

You are Codex operating on the IBKR Trading System repository.

Your task is to extend the RunEventTimeline with **event filtering and query
capabilities**. This enables precise inspection of event streams without
changing execution behaviour.

This step builds on Phase 8 Step 8.4 aggregation APIs.

---

## OBJECTIVE

You will add read-only query helpers that allow:

- Filtering events by type
- Filtering events by source
- Filtering events by arbitrary predicate (advanced use)

These APIs are for observability, debugging, and governance only.

---

## FILES TO MODIFY

You must modify **only** the following file:

- `src/core/run_event_timeline.py`

No other files may be changed.

---

## STEP 1 — FILTER BY EVENT TYPE

Inside `RunEventTimeline`, add:

```python
def filter_by_type(self, event_type: str) -> list:
    return [event for event in self._events if event.event_type == event_type]

STEP 2 — FILTER BY SOURCE

Add a source-based filter:

def filter_by_source(self, source: str) -> list:
    return [event for event in self._events if event.source == source]

STEP 3 — GENERIC FILTER (PREDICATE)

Add an advanced generic filter:

from typing import Callable

def filter(self, predicate: Callable) -> list:
    return [event for event in self._events if predicate(event)]


This enables future tooling such as:

Time-range filtering

Confidence-based inspection

Strategy-specific diagnostics

STEP 4 — SAFETY & STYLE RULES

Ensure:

All filters are read-only

_events is never mutated

No logging or printing inside filters

No changes to event ordering

Return lists preserve original event order

VALIDATION REQUIREMENTS

After implementation:

Filtering returns correct subsets

Aggregation APIs from Step 8.4 still work

No side effects occur during filtering

System output remains unchanged unless filters are explicitly called

COMPLETION CRITERIA

This step is complete when:

Filtering APIs exist and work correctly

Timeline remains deterministic

No existing execution or replay logic is touched

System runs without regression

Do not proceed to the next step until this is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. Copy **everything** in the block above  
2. Paste into **Codex**  
3. Let Codex implement it  
4. Run the system once (behaviour unchanged)

When complete, reply **exactly** with:

> **“STEP 8.5 complete — ready for Phase 8 Step 8.6”**

You are now building a **queryable event ledger** — a prerequisite for analytics, audits, dashboards, and ML pipelines.

We proceed when you confirm.
