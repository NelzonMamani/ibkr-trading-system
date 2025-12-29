📄 PHASE_10_STEP_10_2_MINIMUM_HOLD_DURATION.md
# PHASE 10 — REAL TRADE LIFECYCLES
## STEP 10.2 — MINIMUM HOLD DURATION (TICK-BASED SAFETY)

### OBJECTIVE
Introduce a mandatory minimum hold duration for all open trades so that:
- No trade can be closed in the same tick it was opened
- Exit logic respects a time-based safety floor
- Trade lifecycle realism is enforced without strategy logic

This step builds directly on STEP 10.1, which already removed immediate exits.

---

### DESIGN PRINCIPLES

1. Trade lifecycle authority remains with TradeExitEngine
2. ExecutionEngine MUST NOT enforce holding rules
3. Minimum hold duration must be:
   - Tick-based (not time-based)
   - Configurable
   - Enforced centrally
4. Default behaviour must be SAFE and deterministic

---

### CONFIGURATION

Add a new configuration value:

File: `src/config/trading_config.py`

```python
MIN_HOLD_TICKS: int = 2


Meaning:

A trade opened at tick N cannot be closed until tick >= N + MIN_HOLD_TICKS

DATA MODEL REQUIREMENTS

Ensure every active trade already stores:

entry_tick (already present)

No schema changes are required.

IMPLEMENTATION REQUIREMENTS
1. Modify TradeExitEngine

File: src/core/trade_exit_engine.py

Before closing a trade, enforce:

current_tick = clock.current_tick
hold_duration = current_tick - trade.entry_tick

if hold_duration < MIN_HOLD_TICKS:
    SKIP exit for this trade


This must:

Silently skip exit evaluation

Not emit TRADE_CLOSED

Not unregister the trade

Not affect other trades

2. Logging (Teaching-Friendly)

When a trade is skipped due to minimum hold:

[EXIT][HOLD] symbol=ABC hold_ticks=1 < min_required=2 — exit deferred


This log is OPTIONAL but recommended.

EVENT INTEGRITY RULES

NO TRADE_CLOSED event may be emitted before minimum hold duration

TRADE_EXIT_COMPLETE should still fire even if zero trades close

Registry state must remain consistent

SAFETY INVARIANTS

After implementation:

entry_tick == exit_tick is impossible

exit_tick - entry_tick >= MIN_HOLD_TICKS

Replay reconstruction must still pass invariants

System must run unchanged in SIM mode

ACCEPTANCE CRITERIA

Run the system for multiple ticks and verify:

Trades persist across at least MIN_HOLD_TICKS

Performance counters increment only after valid exits

Replay output shows delayed TRADE_CLOSED events

No crashes, no config ambiguity, no duplicated logic

NON-GOALS (DO NOT IMPLEMENT)

Stop losses

Profit targets

Strategy exits

Time-based (seconds/minutes) exits

Broker integration changes

These belong to later steps.

COMPLETION STATEMENT

When complete, the system must demonstrate:

Realistic holding behaviour

Explicit lifecycle control

Clean separation of concerns

Readiness for Phase 10.3

END OF STEP 10.2


---

## ✅ What to do now

1. **Copy the entire block above**
2. Paste it into Codex
3. Let Codex implement **exactly this**
4. Run the system for ≥ 3 ticks
5. Paste me the runtime output

Once verified, we will proceed cleanly to:

### **Phase 10 · Step 10.3 — Time-Based Exit Rules**

You are doing this properly. We’re past the hard part now.