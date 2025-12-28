✅ Minimal “Phase 9 Closure Patch” (do this before Phase 10)

Copy/paste this into Codex as one final Phase 9 patch:

# PHASE 9 — FINAL CLOSURE PATCH (SHUTDOWN_COMPLETE + SNAPSHOT CONSISTENCY)

You are Codex working on the IBKR trading system repo.

Goal: finish Phase 9 by adding SHUTDOWN_COMPLETE and aligning Strategy snapshot win/loss/flat logic.

Do not add new features. Minimal changes only.

## A) Add SHUTDOWN_COMPLETE event type

File: src/events/event_types.py
- Add new event type constant: SHUTDOWN_COMPLETE

## B) Emit SHUTDOWN_COMPLETE during graceful shutdown

File: src/core/orchestrator.py
- In the KeyboardInterrupt / graceful shutdown path:
  - ensure SHUTDOWN_REQUESTED is emitted first (already)
  - ensure SHUTDOWN_STARTED is emitted next (already)
  - AFTER:
      execution_engine.shutdown()
      trade_exit_engine.shutdown()
      storage_engine.shutdown()
      registry verification pass
    emit SHUTDOWN_COMPLETE
- Ensure EventCollector includes it in shutdown summary.
- Ensure shutdown events are NOT included in cycle replay (out-of-cycle).

## C) Align STRATEGY_PERF_SNAPSHOT counts with flats

File: src/core/orchestrator.py (or wherever strategy perf snapshot is constructed)
- When building strategy snapshot, classify results as:
  - pnl > 0 => win
  - pnl < 0 => loss
  - pnl == 0 => flat
- Ensure totals match the PerformanceRegistry by_strategy values.

## Acceptance
- After running and Ctrl+C:
  - shutdown by_type includes SHUTDOWN_COMPLETE
  - shutdown lifecycle is REQUESTED -> STARTED -> COMPLETE
  - Strategy snapshot no longer counts flat pnl as losses

After you apply that patch, you can proceed to Phase 10

Because then Phase 9 will satisfy all closure requirements:

ExecutionResult reflects closure ✅

PERF_SNAPSHOT authoritative ✅

Replay deterministic ✅

Shutdown lifecycle complete ✅ (after patch)

No active trades remain ✅

Once you paste the new run output showing SHUTDOWN_COMPLETE, tell me and I’ll say:

“PHASE 9 COMPLETE — READY FOR PHASE 10.”