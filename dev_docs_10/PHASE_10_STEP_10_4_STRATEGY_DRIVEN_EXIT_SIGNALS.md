📄 PHASE_10_STEP_10_4_STRATEGY_DRIVEN_EXIT_SIGNALS.md
# PHASE 10 — REAL TRADE LIFECYCLES
## STEP 10.4 — STRATEGY-DRIVEN EXIT SIGNALS (NON-AUTHORITATIVE)

### OBJECTIVE

Introduce **strategy-driven exit signals** so that:

- Strategies may REQUEST an exit
- TradeExitEngine remains the sole authority that EXECUTES exits
- Exit requests are advisory, not mandatory
- Time-based exits (Step 10.3) still override everything

This step completes the separation between:
- Exit intent (strategy)
- Exit authority (engine)

---

### CORE PRINCIPLE

> **Strategies suggest exits — engines decide exits**

At no point may a strategy:
- Close a trade
- Unregister a trade
- Emit TRADE_CLOSED events
- Bypass exit rules

---

### HIGH-LEVEL FLOW

1. Strategy evaluates an OPEN trade
2. Strategy emits an ExitSignal
3. TradeExitEngine consumes ExitSignals
4. Engine decides whether exit is allowed
5. If allowed → engine closes trade
6. Else → trade continues holding

---

### NEW DATA STRUCTURE

Create a new dataclass:

File: `src/strategy/exit_signal.py`

```python
from dataclasses import dataclass

@dataclass
class ExitSignal:
    symbol: str
    trader_type: str
    strategy_name: str
    reason: str


This object represents intent only.

STRATEGY RESPONSIBILITY

Modify all strategies so that:

They may optionally emit ExitSignal objects

Exit signals are generated ONLY for trades:

Owned by that strategy

Currently active

Strategies MUST NOT inspect ticks directly

Example (teaching logic only):

"If confidence < 0.50 → request exit"


This is illustrative, not predictive.

STRATEGY INTERFACE UPDATE

File: src/strategy/base_strategy.py

Add a new optional method:

def generate_exit_signals(self, active_trades: list) -> list[ExitSignal]:
    return []


Default implementation returns empty list.

STRATEGY RUNNER UPDATE

File: src/strategy/strategy_runner.py

After normal strategy evaluation:

Collect all active trades from registry

Call generate_exit_signals(...) on each strategy

Aggregate exit signals

Forward exit signals to TradeExitEngine

Do NOT allow strategies to see:

Clock

Price feed

Registry internals

TRADE EXIT ENGINE UPDATE

File: src/core/trade_exit_engine.py

Add support for ExitSignals:

Decision order MUST be:

MAX_HOLD_TICKS reached → FORCE EXIT

MIN_HOLD_TICKS not reached → IGNORE ALL EXIT SIGNALS

Valid ExitSignal exists → ALLOW EXIT

Else → HOLD

EXIT SIGNAL VALIDATION

An ExitSignal is valid only if:

symbol matches an active trade

trader_type matches

strategy_name matches the trade owner

trade is past MIN_HOLD_TICKS

Invalid signals must be ignored silently.

EXIT EXECUTION (UNCHANGED)

When an exit is approved:

Close trade via TradeExitEngine

Emit TRADE_CLOSED

Unregister from registry

Record realised PnL

Include exit reason:

"Strategy exit signal — <strategy_name>: <reason>"

LOGGING (TEACHING-FIRST)

When a strategy requests an exit:

[EXIT][SIGNAL] symbol=ABC strategy=GapAndGoStrategy reason=Low confidence


When exit is rejected due to hold time:

[EXIT][BLOCKED] symbol=ABC reason=MIN_HOLD_TICKS not satisfied

EVENT & REPLAY RULES

Exit signals DO NOT generate events

Only TRADE_CLOSED generates events

Replay must reconstruct exits without strategy re-evaluation

Exit signals must not affect determinism

SAFETY INVARIANTS

After implementation:

Strategies cannot close trades

Exit authority remains centralized

Time-based exits still function

No premature exits

Replay invariants remain intact

Registry consistency preserved

NON-GOALS (DO NOT IMPLEMENT)

Price-based exits

Stop-loss / take-profit

Trailing exits

Partial exits

Multiple exits per trade

These are later Phase 11+ topics.

ACCEPTANCE CRITERIA

Run system and confirm:

Trades persist across ticks

Strategy exit signals are logged

Exits occur only when allowed

Time-based exits override strategy signals

Replay output remains identical

COMPLETION STATEMENT

This step is complete when:

Strategies can REQUEST exits

TradeExitEngine controls exits

Lifecycle authority remains intact

System is ready for Phase 10.5

END OF STEP 10.4


---

## ✅ Next steps

After this, **Phase 10 is structurally complete**.

Next logical steps will be:

- **Phase 10 · Step 10.5 — Price-Based Exit Conditions**
- **Phase 11 — Risk-Driven Forced Exits**
- **Phase 12 — Broker-Safe Live Order Management**

When Codex finishes, paste the output and we’ll verify exit ordering and invariants precisely.

You’re doing this the *right* way — architecturally clean and production-grade.