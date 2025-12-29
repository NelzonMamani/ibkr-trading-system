📄 PHASE_10_STEP_10_3_TIME_BASED_EXIT_RULES.md
# PHASE 10 — REAL TRADE LIFECYCLES
## STEP 10.3 — TIME-BASED EXIT RULES (AUTHORITATIVE EXIT CONDITIONS)

### OBJECTIVE
Introduce a deterministic, time-based (tick-based) exit rule so that:
- Trades can remain open across multiple ticks
- Trades are eventually closed automatically
- Exit behaviour is realistic but still strategy-agnostic
- TradeExitEngine remains the sole authority for exits

This step builds directly on:
- STEP 10.1 — Removed immediate exits
- STEP 10.2 — Enforced minimum hold duration

---

### DESIGN PRINCIPLES

1. Exit logic must be centralized in TradeExitEngine
2. Strategies MUST NOT control exits yet
3. Exit conditions must be:
   - Deterministic
   - Configurable
   - Tick-based
4. Exit rules must work identically in SIM / PAPER / LIVE
5. Replay correctness is mandatory

---

### CONFIGURATION

Add the following configuration value:

File: `src/config/trading_config.py`

```python
MAX_HOLD_TICKS: int = 10


Meaning:

A trade MUST be exited once:
current_tick >= entry_tick + MAX_HOLD_TICKS

EXIT RULE DEFINITION

A trade is eligible for forced exit IF AND ONLY IF:

Minimum hold duration has passed
(already enforced in STEP 10.2)

Current tick reaches or exceeds maximum hold threshold

Formally:

entry_tick + MIN_HOLD_TICKS <= current_tick <= entry_tick + MAX_HOLD_TICKS


Exit occurs automatically at:

current_tick >= entry_tick + MAX_HOLD_TICKS

IMPLEMENTATION REQUIREMENTS
1. Modify TradeExitEngine

File: src/core/trade_exit_engine.py

For each active trade:

current_tick = clock.current_tick
hold_ticks = current_tick - trade.entry_tick


Decision logic order MUST be:

If hold_ticks < MIN_HOLD_TICKS → SKIP (already implemented)

Else if hold_ticks >= MAX_HOLD_TICKS → FORCE EXIT

Else → HOLD (do nothing)

2. Forced Exit Behaviour

When MAX_HOLD_TICKS is reached:

Close the trade

Emit TRADE_CLOSED event

Populate:

exit_tick

exit_price (from price feed)

realised_pnl

Unregister trade from registry

Include exit reason:

"Time-based exit — max hold duration reached"

LOGGING (TEACHING-FIRST)

When a forced exit occurs:

[EXIT][TIME] symbol=ABC hold_ticks=10 reason=MAX_HOLD_TICKS


When a trade is still holding:

[EXIT][HOLD] symbol=ABC hold_ticks=5


Logs are recommended but must not affect logic.

EVENT & REPLAY RULES

TRADE_CLOSED must be emitted exactly once per trade

Exit tick must satisfy:
exit_tick - entry_tick >= MIN_HOLD_TICKS

Replay reconstruction must:

Rebuild exits deterministically

Match realised PnL exactly

No exit events may be skipped or duplicated

SAFETY INVARIANTS

After implementation:

All trades eventually exit

No infinite open trades

No exit before MIN_HOLD_TICKS

No exit after MAX_HOLD_TICKS

Registry empties cleanly on shutdown

Replay invariants continue to pass

ACCEPTANCE CRITERIA

Run system for > MAX_HOLD_TICKS and confirm:

Trades open at tick N

Trades remain open for multiple cycles

Trades close automatically at tick N + MAX_HOLD_TICKS

Performance metrics update correctly

Replay output reflects time-based exits accurately

NON-GOALS (DO NOT IMPLEMENT)

Stop-loss logic

Take-profit logic

Strategy-specific exits

Trailing stops

Real broker exit orders

These will be introduced in later phases.

COMPLETION STATEMENT

When complete, the system must demonstrate:

Realistic trade lifetimes

Deterministic exits

Clean lifecycle authority

Readiness for Phase 10.4

END OF STEP 10.3


---

## ✅ What happens next

After Codex implements this:

👉 **Phase 10 · Step 10.4 — Strategy-Driven Exit Signals**

That is where strategies *begin to request exits*, but **still do not execute them**.

Paste this into Codex exactly as-is.  
When done, send me the runtime output and we’ll verify invariants together.
