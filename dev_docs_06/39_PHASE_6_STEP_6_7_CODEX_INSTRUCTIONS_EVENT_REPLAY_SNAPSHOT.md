# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.7 — EVENT SNAPSHOT & REPLAY FOUNDATION

You are Codex operating on the IBKR Trading System repository.

Your task is to add **event snapshot capability**
so each cycle can be replayed or inspected deterministically.

This is NOT a full replay engine yet.
It is the foundation.

---

## GLOBAL OBJECTIVE

You will:

- Add snapshot export capability
- Preserve event ordering
- Avoid persistence or files
- Keep everything in-memory
- Maintain teaching-first clarity

---

## FILES TO MODIFY

Modify **only**:

- `src/core/event_collector.py`
- `src/core/orchestrator.py`

---

## STEP 1 — ADD SNAPSHOT METHOD

In `event_collector.py`, add:

```python
def snapshot(self):
    print("[EVENT_COLLECTOR] Snapshotting events")
    return list(self._events)
```

---

## STEP 2 — EXPOSE SNAPSHOT AT CYCLE END

In `orchestrator.py`, after EVENT_SUMMARY, add:

```python
snapshot = self.event_collector.snapshot()
print(
    f"[EVENT_SNAPSHOT] Captured "
    f"{len(snapshot)} events for replay"
)
```

Do NOT store it yet.

---

## VALIDATION REQUIREMENTS

After implementation:

- Snapshot size matches event count
- Order preserved
- No mutation occurs
- Snapshot resets per cycle

---

## COMPLETION CRITERIA

This step is complete when:

- Each cycle produces a snapshot
- Snapshot count matches summary
- System remains deterministic

---

## ✅ NEXT ACTION

1. Copy entire file
2. Paste into Codex
3. Run the system
4. Confirm snapshot logs appear

Reply with:

> **“STEP 6.7 complete — event snapshot foundation ready”**
