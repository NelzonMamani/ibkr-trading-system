# 39_PHASE_7_STEP_7_3_CODEX_INSTRUCTIONS_CYCLE_SUMMARY_PNL_AND_EVENT_COUNTS.md

# PHASE 7 — TIME & PNL FOUNDATIONS
## STEP 7.3 — END-OF-CYCLE SUMMARY: OPENED/CLOSED COUNTS + TOTAL REALISED PNL

You are Codex operating on the IBKR Trading System repository.

You will implement a teaching-only end-of-cycle summary that aggregates:
- number of trades opened this cycle
- number of trades closed this cycle
- total realised pnl this cycle (SIM only)

This uses events emitted during the cycle.

---

## OBJECTIVE

You will:

- Enhance EventCollector to summarise events by type
- Compute total realised PnL from TRADE_CLOSED events (SIM-only)
- Print a clean “cycle summary” block at end of orchestrator cycle
- Keep replay stable and deterministic

---

## FILES TO MODIFY (ONLY THESE)

- src/events/event_collector.py (or wherever EventCollector lives)
- src/orchestrator/orchestrator.py

Do not modify any other files.

---

## STEP 1 — ADD EVENT AGGREGATION HELPERS TO EventCollector

Modify EventCollector to provide:

- count(event_type: str) -> int
- sum_realised_pnl() -> float

Rules:
- sum_realised_pnl sums only TRADE_CLOSED payload["realised_pnl"] if present
- If missing, treat as 0.0
- Always round to 2 decimals at the end

Add logs inside summary only, not per event.

---

## STEP 2 — PRINT CYCLE SUMMARY BLOCK IN ORCHESTRATOR

Modify:

src/orchestrator/orchestrator.py

At the end of run_once(), after existing EVENT_SUMMARY lines, print:

Example (exact formatting required):

```text
[CYCLE_SUMMARY] opened=3 closed=3 realised_pnl=0.00 run_mode=SIM tick=1
```

Rules:
- opened uses TRADE_OPENED count
- closed uses TRADE_CLOSED count
- realised_pnl uses sum_realised_pnl() but ONLY if run_mode == SIM
- If not SIM, realised_pnl must print as "N/A"

So in LIVE:

```text
[CYCLE_SUMMARY] opened=0 closed=0 realised_pnl=N/A run_mode=LIVE tick=123
```

---

## VALIDATION REQUIREMENTS

Run SIM once and confirm you see:

- TRADE_OPENED events
- TRADE_CLOSED events
- CYCLE_SUMMARY with opened/closed/pnl

Replay must remain deterministic.

---

## COMPLETION MESSAGE

When done, respond with:

“PHASE 7 STEP 7.3 complete — ready for Step 7.4”
