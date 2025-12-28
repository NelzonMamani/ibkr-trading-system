📄 FILE: PHASE_9_STEP_9_3_EVENT_PERF_EVENTS.md
# PHASE 9 — STEP 9.3
# Emit Performance Events (Teaching Observability)

## OBJECTIVE
Extend the EventCollector stream so performance reporting is observable and replayable.
After each cycle completes and performance snapshot is computed (Step 9.2),
emit a SYSTEM event summarising performance.

This step MUST NOT change trading logic, registry rules, execution, exit timing, or configs.
It ONLY adds performance-related events and keeps output consistent.

---

## REQUIRED CHANGES

### 1) Add new SystemEvent types (constants or enums, depending on current project style)

Locate existing event typing conventions:
- If you have an EventType enum or constants file, extend it.
- If event_type is plain strings, use new string constants.

Add these event types:
- PERF_SNAPSHOT
- PERF_CYCLE_SUMMARY

Definitions:
- PERF_SNAPSHOT: emitted once per cycle after snapshot computed
- PERF_CYCLE_SUMMARY: optional (if you already have cycle summary event; if not, skip)

---

### 2) Emit PERF_SNAPSHOT event after TradeExit + PerformanceRegistry update

Modify:
src/core/orchestrator.py

After:
- trade_outcomes produced by TradeExitEngine
- performance_registry.record(trade_outcomes)
- snapshot = performance_registry.snapshot()

Emit via EventCollector something like:
SystemEvent(
  event_type="PERF_SNAPSHOT",
  source="PerformanceRegistry",
  payload={
    "total_trades": snapshot.total_trades,
    "wins": snapshot.wins,
    "losses": snapshot.losses,
    "flats": snapshot.flats,
    "win_rate": snapshot.win_rate,
    "gross_pnl": snapshot.gross_pnl,
    "avg_pnl_per_trade": snapshot.avg_pnl_per_trade,
    "by_strategy": snapshot.by_strategy,
    "by_trader_type": snapshot.by_trader_type,
  }
)

Rules:
- payload must be JSON-serialisable (use plain dicts, ints, floats, strings)
- win_rate should be rounded to 4dp in payload (optional but preferred)
- gross_pnl and avg_pnl_per_trade rounded to 4dp in payload (optional but preferred)

---

### 3) Ensure event snapshot is included in replay data

Wherever events are captured for replay in your current code:
- confirm PERF_SNAPSHOT is included automatically (it should be if it’s just another SystemEvent)
- do not add special-case filters that would exclude it

If there is a whitelist of event types for replay:
- add PERF_SNAPSHOT to it

---

### 4) Update console event summary printing (light touch)

Where you print event summaries per cycle:
- ensure PERF_SNAPSHOT appears in the event list
- do NOT print the full payload (too noisy)
- just print the timestamp + event_type + source as you already do

Example expected line in event summary:
... | PERF_SNAPSHOT | PerformanceRegistry

---

## SAFETY CONSTRAINTS (MANDATORY)

- Do NOT change:
  - trade selection
  - risk gating
  - execution behaviour
  - exit behaviour
  - active trade registry rules
- Keep LIVE mode safe and teaching-only.
- No persistence/storage changes.
- PerformanceRegistry remains the single source of truth for computed totals.

---

## EXPECTED RESULT

After Step 9.3:
- Each cycle emits PERF_SNAPSHOT after exit and after snapshot computation
- Event summaries list PERF_SNAPSHOT
- Replay captures it like any other SystemEvent

Report back exactly:
"STEP 9.3 complete — ready for Phase 9 Step 9.4"


Paste that into Codex as-is. After it finishes, run main.py and confirm you see a PERF_SNAPSHOT entry in [EVENT_SUMMARY].