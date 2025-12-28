📄 FILE: PHASE_9_STEP_9_2_PERFORMANCE_REGISTRY.md
# PHASE 9 — STEP 9.2
# Performance Registry (Aggregating Realised Outcomes)

## OBJECTIVE
Add a single, authoritative in-memory PerformanceRegistry that aggregates
TradeOutcome objects produced in Step 9.1.

This step must NOT change strategy, risk, execution, exit logic, or configs.
It only records outcomes after trades are CLOSED.

---

## REQUIRED CHANGES

### 1) Create PerformanceSnapshot model

Create file:
src/domain/performance_snapshot.py

Define a dataclass PerformanceSnapshot with fields:

- total_trades: int
- wins: int
- losses: int
- flats: int
- win_rate: float                 # wins / total_trades (0.0 if total=0)
- gross_pnl: float                # sum of realised_pnl
- avg_pnl_per_trade: float        # gross_pnl / total_trades (0.0 if total=0)

Per-strategy / per-trader_type:
- by_strategy: dict[str, dict[str, float|int]]  # summary buckets
- by_trader_type: dict[str, dict[str, float|int]]

Bucket minimum keys:
- total_trades
- wins
- losses
- flats
- win_rate
- gross_pnl
- avg_pnl_per_trade

---

### 2) Create PerformanceRegistry (single source of truth)

Create file:
src/core/performance_registry.py

Implement a class PerformanceRegistry with:

- __init__(): sets internal list storage for outcomes
- record(outcomes: list[TradeOutcome]) -> None
  - Appends outcomes
  - No duplicates prevention required yet (keep it simple)
- snapshot() -> PerformanceSnapshot
  - Computes all totals and breakdowns deterministically

Rules:
- win/loss/flat classification uses TradeOutcome.outcome
- win_rate is wins/total_trades
- Use float math; guard division by zero

This class must:
- Have no side effects besides storing outcomes
- Not depend on config
- Not import orchestrator
- Not emit events
- Not log

---

### 3) Integrate registry into orchestrator lifecycle

Modify:
src/core/orchestrator.py

Add:
- self.performance_registry = PerformanceRegistry()

After TradeExitEngine closes trades and produces trade_outcomes:
- Call self.performance_registry.record(trade_outcomes)

Then:
- Build a snapshot each cycle (after record)
- Print a concise teaching summary (stdout) with:
  - total_trades, wins, losses, flats, win_rate, gross_pnl, avg_pnl_per_trade
  - plus one-line per strategy gross_pnl (optional, but preferred)

IMPORTANT:
- Keep prints consistent with existing logging style: [PERF] prefix
- Do not spam per-trade lines (only summary)

---

### 4) Extend cycle summary output

Modify wherever cycle summary is printed (orchestrator or reporter area):
- Include realised_pnl totals from PerformanceRegistry snapshot
- Replace "realised_pnl=N/A" with:
  realised_pnl=<gross_pnl formatted to 2dp>

But do NOT remove existing fields.

---

### 5) Ensure TradeRecord includes snapshot (optional but recommended)

Modify:
src/domain/trade_record.py

Add optional field (default None):
- performance_snapshot: PerformanceSnapshot | None = None

Then in orchestrator, after snapshot() is generated:
- store it into the TradeRecord as performance_snapshot

This keeps teaching record complete per cycle.

---

## SAFETY CONSTRAINTS (MANDATORY)

- Do NOT alter:
  - registry active trade logic
  - risk limits
  - execution engine behaviour
  - trade exit timing
- The system must still run safely in LIVE mode with teaching-only execution.
- PerformanceRegistry must be the single authoritative aggregator.
- No persistence layer changes yet.

---

## EXPECTED RESULT

After Step 9.2:
- Every cycle that closes trades updates PerformanceRegistry
- Console shows [PERF] summary after TradeExit stage
- Cycle summary shows realised_pnl numeric value (not N/A)
- TradeRecord optionally contains performance_snapshot

When complete, output in console should look like:
[PERF] total=3 wins=2 losses=1 flats=0 win_rate=0.67 gross_pnl=0.12 avg_pnl=0.04

Then report back:
"STEP 9.2 complete — ready for Phase 9 Step 9.3"


When you paste that into Codex, make sure you paste it as a single instruction (exactly as above).
When Codex finishes, run main.py once and send me the [PERF] output lines + the updated [CYCLE_SUMMARY] line, and we’ll proceed to Phase 9 Step 9.3.
