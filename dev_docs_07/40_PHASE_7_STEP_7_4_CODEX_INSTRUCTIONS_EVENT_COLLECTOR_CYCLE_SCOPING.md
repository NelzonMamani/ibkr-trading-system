# 40_PHASE_7_STEP_7_4_CODEX_INSTRUCTIONS_EVENT_COLLECTOR_CYCLE_SCOPING.md

# PHASE 7 — TIME & PNL FOUNDATIONS
## STEP 7.4 — EVENT COLLECTOR: CYCLE-SCOPED VS GLOBAL EVENTS

You are Codex operating on the IBKR Trading System repository.

You will fix event accounting by separating:
- events for the current cycle
- cumulative events (for replay & history)

This resolves incorrect cycle summaries.

---

## OBJECTIVE

You will:

- Introduce explicit cycle-scoped event storage
- Preserve global event history for replay
- Ensure cycle summaries count only current-cycle events
- Maintain deterministic replay behavior

---

## FILES TO MODIFY (ONLY THESE)

- src/events/event_collector.py
- src/orchestrator/orchestrator.py

Do not modify any other files.

---

## STEP 1 — SPLIT EVENT STORAGE IN EventCollector

Modify EventCollector to maintain **two lists**:

- self._cycle_events
- self._all_events

Rules:
- _cycle_events is cleared at cycle start
- _all_events is never cleared
- record_event(event):
  - appends to BOTH lists

Expose methods:

- clear_cycle_events()
- cycle_count(event_type)
- cycle_sum_realised_pnl()
- snapshot_all_events() (existing replay uses this)

---

## STEP 2 — FIX CYCLE CLEARING LOCATION

Modify orchestrator:

Replace any direct clearing logic with:

```python
event_collector.clear_cycle_events()
```

This must happen once per cycle before SCAN.

---

## STEP 3 — UPDATE CYCLE SUMMARY TO USE CYCLE EVENTS ONLY

Modify orchestrator summary logic:

- opened = event_collector.cycle_count("TRADE_OPENED")
- closed = event_collector.cycle_count("TRADE_CLOSED")
- realised_pnl = event_collector.cycle_sum_realised_pnl()

Expected output:

```text
[CYCLE_SUMMARY] opened=3 closed=3 realised_pnl=0.00 run_mode=SIM tick=1
```

---

## VALIDATION REQUIREMENTS

After implementation:

- Cycle summary counts must be correct
- Replay must still show full event history
- No duplicate events
- Deterministic behavior preserved

---

## COMPLETION MESSAGE

When done, respond with:

“PHASE 7 STEP 7.4 complete — ready for Step 7.5”
