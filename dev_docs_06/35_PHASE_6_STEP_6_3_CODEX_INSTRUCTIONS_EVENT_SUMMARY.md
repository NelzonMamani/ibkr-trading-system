# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.3 — EVENT SUMMARY AT CYCLE END

You are Codex operating on the IBKR Trading System repository.

Your task is to add a **cycle-end event summary**
so operators can immediately see what happened during a cycle.

This improves observability without affecting execution.

---

## GLOBAL OBJECTIVE

You will:

- Emit a summary print at the end of each cycle
- Use EventCollector as the source of truth
- Preserve teaching-first clarity
- Avoid persistence or async logic

---

## FILES YOU MAY MODIFY

You must modify **only**:

- `src/core/orchestrator.py`

---

## STEP 1 — ADD CYCLE SUMMARY PRINT

Modify:

📄 `src/core/orchestrator.py`

At the **very end** of `run_once()` (just before returning):

Add:

```python
print(
    f"[EVENT_SUMMARY] Cycle produced {self.event_collector.count()} total events"
)
```

Then optionally print a breakdown:

```python
for event in self.event_collector.snapshot():
    print(
        f"[EVENT_SUMMARY] {event.timestamp} | {event.event_type} | {event.source}"
    )
```

---

## DESIGN CONSTRAINTS

- No mutation of events
- No clearing of collector yet
- No filtering
- Printing only

---

## VALIDATION REQUIREMENTS

After implementation:

- Each cycle ends with a readable event summary
- Order is chronological
- Output is deterministic
- No impact on trading logic

---

## COMPLETION CRITERIA

This step is complete when:

- Each cycle prints a full event summary
- Counts match observed emissions
- Collector remains intact

---

## ✅ NEXT ACTION

1. Copy this entire file
2. Paste into Codex
3. Run the system
4. Confirm summaries appear after each cycle

When complete, reply:

> **“STEP 6.3 complete — event summaries visible”**
