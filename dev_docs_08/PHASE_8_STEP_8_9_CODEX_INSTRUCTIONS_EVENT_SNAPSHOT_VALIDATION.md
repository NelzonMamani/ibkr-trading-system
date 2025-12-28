PHASE_8_STEP_8_9_CODEX_INSTRUCTIONS_EVENT_SNAPSHOT_VALIDATION.md
PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.9 — EVENT SNAPSHOT VALIDATION & INTEGRITY CHECKS
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.9 — EVENT SNAPSHOT VALIDATION & INTEGRITY CHECKS

You are Codex operating on the IBKR Trading System repository.

Your task is to add **lightweight validation helpers** that confirm
the structural integrity of exported event snapshots.

This step ensures exported snapshots are:
- Internally consistent
- Deterministic
- Safe for downstream audit, replay, or persistence

No runtime behaviour, logging, or execution flow may be altered.

---

## OBJECTIVE

You will:

- Validate snapshot structure (cycle & run)
- Validate event ordering and counts
- Validate JSON-serializability assumptions
- Keep validation explicit and opt-in (not automatic)

---

## FILES TO MODIFY

You must modify **only** the following file:

- `src/core/run_event_timeline.py`

Do not modify any other files.

---

## STEP 1 — ADD SNAPSHOT VALIDATOR

Inside `RunEventTimeline`, add the following method:

```python
def validate_snapshot(self, snapshot: dict) -> None:
    """
    Validate the structural integrity of an exported event snapshot.

    Raises ValueError if the snapshot is invalid.
    """

    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be a dictionary")

    required_keys = {"scope", "event_count", "events"}
    if not required_keys.issubset(snapshot.keys()):
        raise ValueError("Snapshot missing required keys")

    if snapshot["scope"] not in {"CYCLE", "RUN"}:
        raise ValueError("Snapshot scope must be 'CYCLE' or 'RUN'")

    events = snapshot["events"]
    if not isinstance(events, list):
        raise ValueError("Snapshot events must be a list")

    if snapshot["event_count"] != len(events):
        raise ValueError("Snapshot event_count does not match events length")


Rules:

Do not return anything

Validation is strict and explicit

Raise errors early and clearly

STEP 2 — ADD CONVENIENCE VALIDATORS

Add two thin wrapper methods:

def validate_latest_cycle_snapshot(self) -> None:
    snapshot = self.export_latest_cycle_snapshot()
    self.validate_snapshot(snapshot)


def validate_run_snapshot(self) -> None:
    snapshot = self.export_run_snapshot()
    self.validate_snapshot(snapshot)


Rules:

Do not cache snapshots

Do not mutate timeline state

Do not print or log

STEP 3 — DESIGN CONSTRAINTS (MANDATORY)

Ensure that:

Validation is never auto-invoked

No side effects occur

No imports are added

No configuration flags are introduced

This step must remain purely observational.

VALIDATION REQUIREMENTS

After implementation:

Both snapshot types validate cleanly during normal operation

Invalid snapshots raise clear ValueErrors

Timeline behaviour remains unchanged

Phase 8 observability chain is now integrity-safe

COMPLETION CRITERIA

This step is complete when:

Snapshots can be validated before export

No runtime output changes occur

Phase 8 observability is audit-grade

Do not proceed until this step is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. Copy the **entire block above**
2. Paste it into **Codex**
3. Let Codex apply the changes
4. Run at least one cycle (no output should change)

When finished, reply **exactly** with:

> **“STEP 8.9 complete — ready for Phase 8 Step 8.10”**

You are now entering the **final consolidation layer of Phase 8**.
