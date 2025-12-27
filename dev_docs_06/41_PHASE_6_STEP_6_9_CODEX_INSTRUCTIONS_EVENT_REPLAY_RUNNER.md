# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.9 — DETERMINISTIC EVENT REPLAY RUNNER (FOUNDATION)

You are Codex operating on the IBKR Trading System repository.

Your task is to add a **deterministic event replay runner**
that can replay a single cycle’s events in order.

This is NOT a full simulator.
It is a teaching and verification tool.

---

## GLOBAL OBJECTIVE

You will:

- Replay events sequentially
- Preserve event order
- Avoid side effects
- Use prints only
- Keep implementation minimal

---

## FILES TO MODIFY

Modify **only**:

- `src/core/orchestrator.py`

---

## STEP 1 — ADD REPLAY METHOD

Inside Orchestrator, add:

```python
def replay_events(self, events):
    print("[REPLAY] Starting deterministic event replay")

    for event in events:
        print(
            f"[REPLAY] {event.timestamp} | "
            f"{event.event_type} | {event.source} | "
            f"{event.payload}"
        )

    print("[REPLAY] Replay complete")
```

---

## STEP 2 — CALL REPLAY AFTER SNAPSHOT (TEACHING ONLY)

After snapshot capture in `run_once()`:

```python
self.replay_events(snapshot)
```

Add a print before calling:

```python
print("[REPLAY] Initiating replay for teaching verification")
```

---

## VALIDATION REQUIREMENTS

After implementation:

- Replay prints all events in order
- No state is mutated during replay
- Replay output matches event summary
- Replay is deterministic

---

## COMPLETION CRITERIA

This step is complete when:

- Replay output matches snapshot
- No side effects occur
- Teaching clarity is achieved

---

## ✅ NEXT ACTION

1. Copy entire file
2. Paste into Codex
3. Run system
4. Verify replay output

Reply with:

> **“STEP 6.9 complete — deterministic replay operational”**
