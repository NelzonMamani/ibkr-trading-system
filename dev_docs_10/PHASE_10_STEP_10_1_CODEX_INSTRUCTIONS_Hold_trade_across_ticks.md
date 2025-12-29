N
ext Phase (Phase 10) — what we do now
Phase 10 is where trades stop being “open and immediately close” and become real lifecycles:
Phase 10 objectives
1. Hold trades across ticks
a trade opened on tick 1 should still be open on tick 2 unless exit conditions trigger.
2. Exit logic becomes explicit and reasoned
time-based stop, stop-loss, take-profit, trailing, breakeven, etc.
3. Event model becomes canonical
TRADE_OPENED, TRADE_UPDATED (optional), TRADE_CLOSED
schema locked, replay covers the lifecycle
4. Trade registry becomes the single source of truth
no “closing by side effects”
exit engine reads registry, writes closure events, unregisters

The next Codex task to move forward (copy/paste)
This is the exact instruction to give Codex now:
# PHASE 10 — REAL TRADE LIFECYCLES (START)
## STEP 10.1 — HOLD TRADES ACROSS TICKS (REMOVE IMMEDIATE EXIT)

Goal:
Trades must persist across cycles/ticks. The TradeExitEngine must NOT close trades immediately in the same tick they are opened.

Instructions:
1) Locate TradeExitEngine logic that closes trades after 1 tick or in the same cycle (teaching-only behaviour).
2) Change it so trades are only closed if an explicit exit condition is met.
3) For now, implement the simplest explicit exit condition:
   - Close only if (current_tick - entry_tick) >= MIN_HOLD_TICKS
4) Add config value MIN_HOLD_TICKS with default = 3.
5) Ensure the following invariants remain true:
   - registry holds open trades across ticks
   - TRADE_CLOSED only emitted when exit triggers
   - deterministic replay still passes invariants
   - schema remains unchanged (do not add/remove event fields)

Deliverable:
- Code changes only; no documentation rewrite.
- After change, run main.py and confirm:
   - tick 1 opens trades
   - ticks 2 and 3 show them still active (no closures)
   - tick 4 closes them due to MIN_HOLD_TICKS

If you paste just the output from tick 1 through tick 5 after Codex applies that change, I’ll validate that Phase 10.1 is correct and then we’ll move to 10.2 (Exit rules: SL/TP).
