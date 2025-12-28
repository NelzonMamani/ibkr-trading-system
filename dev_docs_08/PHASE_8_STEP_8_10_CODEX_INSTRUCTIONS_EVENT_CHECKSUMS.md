PHASE_8_STEP_8_10_CODEX_INSTRUCTIONS_EVENT_CHECKSUMS.md
PHASE 8 — OBSERVABILITY & GOVERNANCE
STEP 8.10 — EVENT SNAPSHOT CHECKSUMS (INTEGRITY SEAL)
🟥 COPY EVERYTHING BELOW INTO CODEX (ONE BLOCK ONLY)
# PHASE 8 — OBSERVABILITY & GOVERNANCE
## STEP 8.10 — EVENT SNAPSHOT CHECKSUMS (INTEGRITY SEAL)

You are Codex operating on the IBKR Trading System repository.

Your task is to add **deterministic checksums** to exported event snapshots
so they can be verified for tampering, corruption, or mutation.

This step adds an integrity seal without persistence, crypto libraries,
or security theatre.

---

## OBJECTIVE

You will:

- Generate a deterministic checksum for snapshots
- Attach the checksum to exported snapshots
- Ensure identical snapshots always produce identical checksums
- Preserve teaching-first clarity

---

## FILES TO MODIFY

You must modify **only** the following file:

- `src/core/run_event_timeline.py`

Do not modify any other files.

---

## STEP 1 — ADD CHECKSUM HELPER

At the top of the file (below existing imports), add:

```python
import json
import hashlib


Then, inside RunEventTimeline, add:

def _compute_snapshot_checksum(self, snapshot: dict) -> str:
    """
    Compute a deterministic checksum for a snapshot.

    Uses sorted JSON serialization to ensure stability.
    """

    serialized = json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


Rules:

Use SHA-256

Do not truncate

Do not log or print

STEP 2 — ATTACH CHECKSUM TO SNAPSHOTS

Modify both snapshot export methods so that:

The checksum is computed after snapshot creation

The checksum is added as a top-level field

Expected structure:

snapshot["checksum"] = self._compute_snapshot_checksum(snapshot)


Apply this to:

export_latest_cycle_snapshot

export_run_snapshot

Do not modify snapshot contents beyond adding checksum.

STEP 3 — UPDATE VALIDATION TO INCLUDE CHECKSUM

Extend validate_snapshot so that:

A missing checksum raises an error

A mismatched checksum raises an error

Add the following logic at the end of validation:

expected = self._compute_snapshot_checksum(
    {k: v for k, v in snapshot.items() if k != "checksum"}
)

if snapshot["checksum"] != expected:
    raise ValueError("Snapshot checksum mismatch")


Rules:

Validation must recompute checksum

Validation must remain explicit (never auto-called)

DESIGN CONSTRAINTS (MANDATORY)

No persistence

No signing keys

No environment variables

No security claims beyond integrity detection

This is an audit seal, not cryptographic authentication.

VALIDATION REQUIREMENTS

After implementation:

Checksums are stable across runs with identical data

Any mutation invalidates the checksum

Snapshot validation catches corruption

Runtime output remains unchanged

COMPLETION CRITERIA

This step is complete when:

Every snapshot includes a checksum

Validation enforces integrity

Phase 8 observability becomes tamper-evident

Do not proceed until this step is complete and verified.


---

### 🟦 YOUR NEXT ACTION

1. Copy the **entire block above**
2. Paste it into **Codex**
3. Let Codex apply the changes
4. Run one cycle and (optionally) validate snapshots manually

When finished, reply **exactly** with:

> **“STEP 8.10 complete — ready for Phase 9”**

You are now **closing Phase 8 with audit-grade observability**.
