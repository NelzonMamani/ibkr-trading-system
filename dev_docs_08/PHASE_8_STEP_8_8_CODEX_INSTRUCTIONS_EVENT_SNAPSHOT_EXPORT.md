PHASE_8_STEP_8_8_CODEX_INSTRUCTIONS_EVENT_SNAPSHOT_EXPORT.md
PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.8 — EVENT SNAPSHOT EXPORT (CYCLE / RUN LEVEL)
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.8 — EVENT SNAPSHOT EXPORT (CYCLE / RUN LEVEL)

You are Codex operating on the IBKR Trading System repository.

Your task is to add **high-level snapshot export helpers**
that package serialized events into meaningful audit units.

This step prepares the system for:
- Run-level auditing
- Cycle-level inspection
- External persistence (future phases)

No storage, files, or databases are introduced.

---

## OBJECTIVE

You will:

- Export the **latest cycle** as a self-contained snapshot
- Export the **entire run** as a self-contained snapshot
- Use previously implemented serialization logic
- Preserve strict determinism and ordering

---

## FILES TO MODIFY

You must modify **only** the following file:

- `src/core/run_event_timeline.py`

Do not modify any other files.

---

## STEP 1 — CYCLE SNAPSHOT EXPORT

Add a method to `RunEventTimeline`:

```python
def export_latest_cycle_snapshot(self) -> dict:
    events = self.get_latest_cycle_events()

    return {
        "scope": "CYCLE",
        "event_count": len(events),
        "events": self.serialize_filtered(events),
    }


Rules:

Use existing APIs only

Do not recompute or infer cycle boundaries

Do not mutate timeline state

STEP 2 — FULL RUN SNAPSHOT EXPORT

Add a second method:

def export_run_snapshot(self) -> dict:
    return {
        "scope": "RUN",
        "event_count": len(self._events),
        "events": self.serialize_all(),
    }


Rules:

Order must exactly match internal timeline order

event_count must reflect serialized length

STEP 3 — SNAPSHOT FORMAT RULES

Snapshots must:

Be plain Python dictionaries

Contain only JSON-safe values

Never include object references

Never include runtime-only fields

SAFETY CONSTRAINTS (MANDATORY)

Ensure that:

No printing or logging is added

No configuration flags are introduced

No replay logic is altered

No side effects occur during export

This step is observational only.

VALIDATION REQUIREMENTS

After implementation:

export_latest_cycle_snapshot() works immediately after a cycle

export_run_snapshot() includes all prior cycles

System runtime behaviour is unchanged

Event ordering is preserved exactly

COMPLETION CRITERIA

This step is complete when:

Snapshots can be passed to JSON.dump without errors

Timeline remains the single source of truth

Phase 8 observability reaches audit-readiness

Do not proceed until this step is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. Copy the **entire block above**
2. Paste it into **Codex**
3. Let Codex implement the changes
4. Run one cycle to confirm no output changes

When done, reply **exactly** with:

> **“STEP 8.8 complete — ready for Phase 8 Step 8.9”**

You’re now one step away from **full replay & audit export capability**.
