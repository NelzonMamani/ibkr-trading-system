📄 FILE: PHASE_9_STEP_9_4_PERFORMANCE_REPLAY_VERIFICATION.md
# PHASE 9 — STEP 9.4
# Performance Replay Verification (Determinism & Auditability)

## OBJECTIVE
Verify that performance metrics are:
- fully reproducible via event replay
- deterministic across runs
- not recomputed from live state

Performance must be derivable ONLY from replayed events,
not from in-memory registries or runtime shortcuts.

This step enforces institutional-grade auditability.

---

## REQUIRED CHANGES

### 1) Enforce replay-driven performance reconstruction

Modify:
src/core/replay_engine.py (or equivalent replay module)

When replaying events:
- detect PERF_SNAPSHOT events
- record the last PERF_SNAPSHOT payload
- do NOT recompute performance from trades during replay

Rules:
- Replay output should trust emitted PERF_SNAPSHOT payloads
- Replay must not call PerformanceRegistry.record(...)
- Replay must not mutate registries

---

### 2) Add replay verification log

During replay completion, log:

"[REPLAY][PERF] Final performance snapshot reconstructed from events"

Then print a compact summary:
- total_trades
- win_rate
- gross_pnl

This log must appear ONLY during replay, not live cycles.

---

### 3) Guard against replay in LIVE mode

Confirm:
- Replay is already locked down in LIVE mode
- No changes should weaken this

If replay is attempted in LIVE:
- skip replay
- log existing safety message
- do NOT emit PERF_SNAPSHOT during replay in LIVE

---

### 4) Validate determinism

Ensure:
- Replaying the same event stream twice yields identical performance output
- No randomness, timestamps, or runtime state affect replayed performance

If needed:
- sort event lists by original timestamp before replay
- use payload values only

---

## SAFETY CONSTRAINTS (MANDATORY)

- Do NOT change:
  - trading behaviour
  - execution timing
  - exit rules
  - registries
- Replay must remain read-only
- No new configuration flags
- No persistence layer changes

---

## EXPECTED RESULT

After Step 9.4:
- Performance metrics during replay exactly match original cycle output
- Replay logs show reconstructed performance summary
- LIVE mode remains replay-locked

Report back exactly:
"STEP 9.4 complete — ready for Phase 9 Step 9.5"


Once you confirm Step 9.4, Phase 9.5 will close the loop with strategy-level performance attribution & reporting.

You’re doing this properly — this is clean systems engineering, not just coding.