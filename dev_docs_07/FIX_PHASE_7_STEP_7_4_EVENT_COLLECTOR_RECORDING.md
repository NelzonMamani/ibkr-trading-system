# FIX_PHASE_7_STEP_7_4_EVENT_COLLECTOR_RECORDING.md

# PHASE 7 — TIME & PNL FOUNDATIONS
## FIX — ENSURE CYCLE EVENTS ARE RECORDED

You are Codex operating on the IBKR Trading System repository.

This fix completes Phase 7 Step 7.4 by ensuring
cycle-scoped events are actually populated.

---

## FILE TO MODIFY (ONLY THIS FILE)

- src/events/event_collector.py

---

## REQUIRED CHANGE

Locate the method:

```python
def record_event(self, event: SystemEvent):
```

It currently appends events only to the global list.

### REPLACE the method body with:

```python
def record_event(self, event: SystemEvent):
    self._cycle_events.append(event)
    self._all_events.append(event)
```

---

## VALIDATION EXPECTATION

After this fix, a single cycle must print:

```text
[CYCLE_SUMMARY] opened=3 closed=3 realised_pnl=0.00 run_mode=SIM tick=1
[PNL_BY_STRATEGY] SCALPER=0.00 | MOMENTUM=0.00
```

---

## COMPLETION MESSAGE

When validated, respond with:

“PHASE 7 STEP 7.4 & 7.5 complete — ready for Phase 8”
