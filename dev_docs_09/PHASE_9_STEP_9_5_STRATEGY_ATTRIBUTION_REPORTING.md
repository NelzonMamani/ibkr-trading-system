📄 FILE: PHASE_9_STEP_9_5_STRATEGY_ATTRIBUTION_REPORTING.md
# PHASE 9 — STEP 9.5
# Strategy-Level Attribution & Reporting (Teaching-First, Audit-Ready)

## OBJECTIVE
Add strategy-level performance attribution so the system can answer:
- Which strategy generated which trades?
- What is the PnL / win-rate / trade count per strategy?
- Can we report this deterministically from events?

This must remain teaching-first and safe:
- no broker calls
- no real market data
- no persistence required

---

## REQUIRED CHANGES

### 1) Ensure trade close events include strategy_name
Confirm that the close lifecycle emits enough data to attribute performance.

If not already present, update close event payload(s) to include:
- symbol
- trader_type
- strategy_name
- entry_price
- exit_price
- pnl (even if simulated)
- opened_at_tick
- closed_at_tick

Events impacted (names may vary):
- TRADE_OPENED
- TRADE_CLOSED
- TRADE_EXIT_COMPLETE (optional summary)

If strategy_name is missing at close:
- obtain it from registry position metadata (stored at open time)
- propagate it into the close event payload

Important: Do NOT change execution logic, only payload completeness.

---

### 2) Add StrategyPerformanceTracker (in-memory aggregation)
Create a small, pure-python tracker that consumes closed trade events.

New file:
src/performance/strategy_performance.py

Implement:
- StrategyPerformanceSnapshot dataclass:
  - strategy_name: str
  - total_trades: int
  - wins: int
  - losses: int
  - gross_pnl: float
  - win_rate: float (computed property)
- StrategyPerformanceTracker:
  - record_trade_close(event_payload) -> None
  - snapshot() -> list[StrategyPerformanceSnapshot]

Rules:
- "win" if pnl > 0
- "loss" if pnl <= 0
- deterministic ordering: sort snapshots by strategy_name

---

### 3) Emit STRATEGY_PERF_SNAPSHOT event each cycle
At end of each orchestrator cycle, after exits, emit an event like:

event_type = "STRATEGY_PERF_SNAPSHOT"
payload = {
  "strategies": [
     {"strategy_name":"GapAndGoStrategy","total_trades":...,"wins":...,"losses":...,"gross_pnl":...,"win_rate":...},
     ...
  ]
}

Where to emit:
- best location is where PERF_SNAPSHOT is emitted (same phase step)
- must occur after TRADE_CLOSED events so stats are complete

The tracker can be cycle-scoped or run-scoped, but must be consistent:
Preferred (teaching-first): run-scoped totals (since boot) + cycle summary log

---

### 4) Update replay to verify strategy attribution determinism
Modify replay engine so it can:
- detect STRATEGY_PERF_SNAPSHOT events
- log a replay summary at the end:

"[REPLAY][STRATEGY] Reconstructed strategy snapshot from events"

Print:
- strategy_name
- total_trades
- win_rate
- gross_pnl

Replay must remain read-only.

---

### 5) Add log output in live run (teaching-friendly)
At end of cycle (normal runtime, not replay), add:

"[PNL_BY_STRATEGY]"
Then print one line per strategy:
- strategy_name: trades=X wins=Y losses=Z win_rate=.. gross_pnl=..

If no trades closed:
- log "N/A"

This must not crash if empty.

---

## SAFETY CONSTRAINTS
- Do NOT add randomness
- Do NOT connect to broker
- Do NOT change execution rules
- Do NOT introduce file persistence
- Replay must remain read-only and deterministic

---

## ACCEPTANCE CHECKS
Run main.py and confirm you see:
- STRATEGY_PERF_SNAPSHOT emitted per cycle (if trades close)
- [PNL_BY_STRATEGY] section printed
- Replay prints deterministic attribution summary
- Results remain stable across repeated runs with identical event streams

Report back exactly:
"STEP 9.5 complete — ready for Phase 9 Step 9.6"


When you reply “STEP 9.5 complete”, I’ll give you Phase 9 Step 9.6, which typically finishes Phase 9 by tightening event schema validation + audit-grade invariants (still teaching-first).
