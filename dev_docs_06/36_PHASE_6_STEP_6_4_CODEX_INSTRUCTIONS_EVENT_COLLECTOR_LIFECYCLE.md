# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.4 — EVENT COLLECTOR LIFECYCLE (PER-CYCLE RESET)

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce a **controlled lifecycle**
for the EventCollector so that each cycle has a clean event scope.

This is REQUIRED for:
- Accurate replay
- Metrics per cycle
- Backtesting consistency

---

## GLOBAL OBJECTIVE

You will:

- Clear collected events at the START of each cycle
- Preserve collector instance (do NOT recreate it)
- Keep prints to show lifecycle transitions
- Maintain deterministic behavior

---

## FILES TO MODIFY

You must modify **only**:

- `src/core/orchestrator.py`

---

## STEP 1 — ADD CLEAR METHOD USAGE

The EventCollector already exists.
You must **reuse it**, not replace it.

At the very start of `run_once()` add:

```python
print("[EVENT_COLLECTOR] Clearing events for new cycle")
self.event_collector._events.clear()
```

⚠️ This is intentional direct access for teaching clarity.
We will encapsulate later.

---

## STEP 2 — VERIFY ORDER

The clear MUST occur:

- After session checks
- Before `CYCLE_START` is emitted

Correct order:

1. Session logic
2. Clear collector
3. Emit CYCLE_START
4. Rest of pipeline

---

## VALIDATION REQUIREMENTS

After implementation:

- Each cycle reports **exactly 4 events**
- No accumulation across cycles
- Logs clearly show clearing
- Event summary remains correct

---

## COMPLETION CRITERIA

This step is complete when:

- Each cycle starts with a clean event list
- Event summary reflects only current cycle
- No regressions occur

---

## ✅ NEXT ACTION

1. Copy entire file
2. Paste into Codex
3. Run the system for 2+ cycles
4. Confirm `[EVENT_COLLECTOR] Clearing events for new cycle` appears

When finished, reply:

> **“STEP 6.4 complete — event lifecycle controlled”**
