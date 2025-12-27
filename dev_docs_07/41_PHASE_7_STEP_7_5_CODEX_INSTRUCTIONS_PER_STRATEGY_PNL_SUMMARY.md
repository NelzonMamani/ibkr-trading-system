# 41_PHASE_7_STEP_7_5_CODEX_INSTRUCTIONS_PER_STRATEGY_PNL_SUMMARY.md

# PHASE 7 — TIME & PNL FOUNDATIONS
## STEP 7.5 — PER-STRATEGY REALISED PNL SUMMARY (SIM)

You are Codex operating on the IBKR Trading System repository.

You will extend cycle summaries to break down realised PnL **per trader_type**.

---

## OBJECTIVE

You will:

- Aggregate realised PnL by trader_type
- Display per-strategy summaries at cycle end
- Use TRADE_CLOSED event payloads only
- Keep SIM-only computation

---

## FILES TO MODIFY (ONLY THESE)

- src/events/event_collector.py
- src/orchestrator/orchestrator.py

Do not modify any other files.

---

## STEP 1 — ADD PNL AGGREGATION BY trader_type

Extend EventCollector with:

- cycle_pnl_by_trader_type() -> dict[str, float]

Rules:
- Iterate over cycle TRADE_CLOSED events
- Group by payload["trader_type"]
- Sum realised_pnl
- Round to 2 decimals

Example return:

```python
{
  "SCALPER": 0.00,
  "MOMENTUM": 0.00
}
```

---

## STEP 2 — PRINT PER-STRATEGY SUMMARY BLOCK

At end of orchestrator cycle, print:

```text
[PNL_BY_STRATEGY] SCALPER=0.00 | MOMENTUM=0.00
```

Rules:
- Order must be deterministic (sorted keys)
- SIM only
- In LIVE mode, print:
  [PNL_BY_STRATEGY] N/A

---

## VALIDATION REQUIREMENTS

- Values must match TRADE_CLOSED events
- Output deterministic
- Replay unaffected

---

## COMPLETION MESSAGE

When done, respond with:

“PHASE 7 STEP 7.5 complete — Phase 7 finished”
