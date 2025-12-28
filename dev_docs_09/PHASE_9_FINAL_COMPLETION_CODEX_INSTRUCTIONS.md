PHASE_9_FINAL_COMPLETION_CODEX_INSTRUCTIONS.md
# PHASE 9 — RUNTIME SAFETY, FAULT TOLERANCE & GRACEFUL SHUTDOWN
## FINAL CONSOLIDATION & CONSISTENCY PATCH (AUTHORITATIVE)

You are Codex operating on the IBKR Trading System repository.

Your task is to COMPLETE Phase 9 by fixing the final structural inconsistencies
so that runtime behaviour, performance accounting, execution results, and
shutdown semantics are fully consistent, deterministic, and auditable.

This is a FINAL Phase 9 consolidation. Do not introduce new features.
Do not change system architecture. Fix correctness only.

---

## GLOBAL OBJECTIVES

After this patch:

- Phase 9 must be internally consistent
- Performance metrics must match execution reality
- Execution results must reflect closed trades correctly
- Event-driven replay must reconstruct identical outcomes
- Graceful shutdown must emit a complete lifecycle
- Phase 10 must be unblocked with zero ambiguity

---

## FILES YOU MAY MODIFY (ONLY THESE)

- `src/execution/execution_engine.py`
- `src/performance/performance_registry.py`
- `src/events/event_types.py`
- `src/core/orchestrator.py`

DO NOT modify any other files.
DO NOT add new subsystems.
DO NOT change strategy, risk, or scanner logic.

---

## PART 1 — FIX EXECUTION RESULT CONSISTENCY (CRITICAL)

### PROBLEM
Trades are CLOSED in SIM mode, but ExecutionResult objects still show:
- exit_price = None
- exit_tick = None

This breaks downstream accounting and performance metrics.

### REQUIRED FIX

In `src/execution/execution_engine.py`:

When a SIM trade is CLOSED:
- Populate ExecutionResult.exit_price
- Populate ExecutionResult.exit_tick
- Populate realised_pnl (if field exists)

Example logic (adapt to your structure):

- When simulating CLOSE:
  - capture close_tick
  - capture close_price
  - set these on the ExecutionResult instance

Ensure:
- Every TRADE_CLOSED event has a matching ExecutionResult with exit info
- No ExecutionResult representing a closed trade has null exit fields

---

## PART 2 — MAKE PERFORMANCE REGISTRY AUTHORITATIVE FROM EVENTS

### PROBLEM
Strategy performance snapshots show trades,
but global PerformanceSnapshot shows total_trades = 0.

This indicates PerformanceRegistry is NOT consuming authoritative events.

### REQUIRED FIX

In `src/performance/performance_registry.py`:

- Treat TRADE_CLOSED events as the single source of truth
- Increment totals when a TRADE_CLOSED event is recorded
- Compute:
  - total_trades
  - wins / losses / flats
  - gross_pnl
  - avg_pnl_per_trade
- Update per-strategy and per-trader_type breakdowns from events

DO NOT rely on `trade_outcomes` lists that may be empty.
DO NOT infer from StrategyRunner outputs.
Events are authoritative.

After this fix:
- PerformanceSnapshot totals MUST match Strategy snapshot totals
- Replay must reconstruct identical performance numbers

---

## PART 3 — COMPLETE SHUTDOWN EVENT LIFECYCLE

### PROBLEM
Shutdown currently emits:
- SHUTDOWN_REQUESTED
- SHUTDOWN_STARTED

But no explicit terminal event exists.

### REQUIRED FIX

In `src/events/event_types.py`:

Add a new event type:

```python
SHUTDOWN_COMPLETE

In src/core/orchestrator.py:


Emit SHUTDOWN_COMPLETE after:


execution shutdown


trade exit shutdown


storage shutdown


registry verification passes




Ensure:


EventCollector captures SHUTDOWN_COMPLETE


It appears in shutdown summaries


It does NOT appear in per-cycle replays (shutdown is out-of-cycle)



PART 4 — INVARIANT VERIFICATION (NO NEW LOGIC)
Ensure the following invariant still holds and is logged:


No active trades remain at shutdown


Registry verification runs before SHUTDOWN_COMPLETE


If invariant fails, emit an ERROR-level event and abort shutdown


DO NOT add retries.
DO NOT add recovery logic.
This is a teaching-first invariant.

VALIDATION REQUIREMENTS (MANDATORY)
After implementation:


ExecutionResult objects always reflect trade closure accurately


PerformanceSnapshot totals match Strategy snapshot totals


Replay reconstructs identical performance metrics


Shutdown emits REQUESTED → STARTED → COMPLETE in order


No active trades remain after shutdown


System exits with code 0


No Phase 9 logs contradict each other



COMPLETION CRITERIA
Phase 9 is COMPLETE when:


Runtime safety is deterministic


Performance accounting is correct


Event replay is lossless


Shutdown is explicit and auditable


No warnings or TODOs remain in Phase 9 scope


DO NOT PROCEED TO PHASE 10 until this patch is complete and verified.

YOUR ACTION


Copy this entire Markdown file


Paste it directly into Codex


Let Codex implement the fixes


Run the system in SIM mode


Verify:


totals align


replay matches live run


shutdown lifecycle is complete




When finished, report:

“PHASE 9 COMPLETE — READY FOR PHASE 10”


---

### 🧭 Final note (important)
Once this is done, **Phase 9 is genuinely finished** — not “working”, not “mostly”, but **institutionally correct**.

When you’re ready, Phase 10 becomes:
> portfolio-level logic, live broker abstraction, and real capital controls — built on something solid.

You did the hard part.
