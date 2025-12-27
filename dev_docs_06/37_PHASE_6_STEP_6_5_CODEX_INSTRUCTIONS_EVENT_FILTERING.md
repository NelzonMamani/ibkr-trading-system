# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.5 — EVENT FILTERING (BY TYPE AND SOURCE)

You are Codex operating on the IBKR Trading System repository.

Your task is to add **non-invasive filtering**
to the EventCollector so consumers can query specific events.

This is foundational for:
- Metrics
- Alerts
- Trade lifecycle tracking
- Replay tooling

---

## GLOBAL OBJECTIVE

You will:

- Add filtering by event_type
- Add filtering by source
- Preserve existing behavior
- Avoid modifying event emission logic

---

## FILES TO MODIFY

You must modify **only**:

- `src/core/event_collector.py`

---

## STEP 1 — ADD FILTER METHODS

Modify `EventCollector` by adding:

```python
def filter_by_type(self, event_type: str):
    return [
        e for e in self._events
        if e.event_type == event_type
    ]
```

And:

```python
def filter_by_source(self, source: str):
    return [
        e for e in self._events
        if e.source == source
    ]
```

---

## STEP 2 — ADD VISIBILITY PRINTS

Inside each filter method, add:

```python
print(
    f"[EVENT_COLLECTOR] Filtering events — type={event_type}"
)
```

and

```python
print(
    f"[EVENT_COLLECTOR] Filtering events — source={source}"
)
```

---

## STEP 3 — OPTIONAL DEMO PRINT (SAFE)

At the end of `run_once()` (after event summary),
add OPTIONAL debug prints:

```python
print(
    f"[EVENT_DEBUG] STRATEGY events: "
    f"{len(self.event_collector.filter_by_source('StrategyRunner'))}"
)
```

This is for teaching visibility only.

---

## VALIDATION REQUIREMENTS

After implementation:

- Filters return correct subsets
- Order is preserved
- No mutation occurs
- Existing functionality unchanged

---

## COMPLETION CRITERIA

This step is complete when:

- EventCollector supports filtered queries
- Logs confirm filtering
- System remains deterministic

---

## ✅ NEXT ACTION

1. Copy entire file
2. Paste into Codex
3. Run the system
4. Confirm filtering logs appear

When finished, reply:

> **“STEP 6.5 complete — event filtering enabled”**
