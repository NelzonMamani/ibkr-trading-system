📄 PHASE_10_STEP_10_5_PRICE_BASED_EXIT_CONDITIONS.md
# PHASE 10 — REAL TRADE LIFECYCLES
## STEP 10.5 — PRICE-BASED EXIT CONDITIONS (ENGINE-ENFORCED)

### OBJECTIVE

Introduce **price-based exit conditions** while preserving strict lifecycle authority.

This step adds:
- Stop-loss exits
- Take-profit exits

All exits remain:
- Engine-enforced
- Deterministic
- Replay-safe
- Strategy-agnostic

---

### CORE PRINCIPLE

> **Prices trigger exits — engines decide exits**

Strategies:
- MAY define price thresholds at entry
- MUST NOT monitor prices
- MUST NOT close trades

TradeExitEngine:
- Is the sole executor of price-based exits

---

### EXIT TYPES INTRODUCED

Each trade may define:

- STOP_LOSS_PRICE (optional)
- TAKE_PROFIT_PRICE (optional)

If neither is defined → trade ignores price exits.

---

### DATA MODEL UPDATE

File: `src/execution/execution_result.py`

Extend `ExecutionResult` to include:

```python
stop_loss_price: float | None
take_profit_price: float | None


These values are FIXED at entry.

STRATEGY RESPONSIBILITY (LIMITED)

Strategies may optionally define exit thresholds at trade creation time.

File: src/strategy/*

When creating TradeIntent:

Include OPTIONAL fields:

stop_loss_price

take_profit_price

Strategies:

Must calculate prices deterministically

Must NOT reference live price feeds

May use confidence-based or static offsets (teaching only)

RISK ENGINE PASS-THROUGH

File: src/risk/risk_engine.py

RiskEngine MUST:

Validate logical correctness:

stop_loss_price < entry_price for LONG

take_profit_price > entry_price for LONG

Reject trades with invalid price geometry

Pass valid prices through unchanged

RiskEngine MUST NOT:

Adjust prices

Trigger exits

Inspect ticks

EXECUTION ENGINE RESPONSIBILITY

File: src/execution/execution_engine.py

At trade entry:

Attach stop_loss_price / take_profit_price to ExecutionResult

Register prices in ActiveTradeRegistry

No price logic occurs here.

ACTIVE TRADE REGISTRY EXTENSION

File: src/core/active_trade_registry.py

Each active trade record MUST store:

symbol
trader_type
strategy_name
direction
entry_price
entry_tick
quantity
stop_loss_price (optional)
take_profit_price (optional)


Registry remains in-memory only.

TRADE EXIT ENGINE — PRICE CHECKS

File: src/core/trade_exit_engine.py

Add price-based checks AFTER time-based rules and BEFORE strategy exit signals.

Decision order MUST be:

MAX_HOLD_TICKS reached → FORCE EXIT

STOP_LOSS_PRICE breached → FORCE EXIT

TAKE_PROFIT_PRICE breached → FORCE EXIT

MIN_HOLD_TICKS not reached → BLOCK STRATEGY EXITS

Valid strategy ExitSignal → ALLOW EXIT

Else → HOLD

PRICE BREACH RULES

For LONG trades:

STOP_LOSS triggers when:

current_price <= stop_loss_price


TAKE_PROFIT triggers when:

current_price >= take_profit_price


(Short trades are NOT implemented in Phase 10.)

EXIT REASON STRINGS

When closing due to price:

Stop loss:

"Stop-loss price breached"


Take profit:

"Take-profit price reached"


These reasons must be included in:

TRADE_CLOSED event payload

TradeOutcome rationale

LOGGING (TEACHING-FIRST)

Examples:

[EXIT][PRICE] symbol=ABC STOP_LOSS hit at 12.10
[EXIT][PRICE] symbol=XYZ TAKE_PROFIT hit at 51.00

EVENT & REPLAY RULES

Price checks occur only in TradeExitEngine

Replay reconstructs exits from TRADE_CLOSED events

No price checks occur during replay

Determinism must be preserved

SAFETY INVARIANTS

After implementation:

Strategies never inspect prices

ExecutionEngine never exits trades

All price exits are engine-enforced

Stop-loss overrides strategy exits

Replay produces identical outcomes

Registry always reflects correct state

NON-GOALS (DO NOT IMPLEMENT)

Trailing stops

Dynamic stop movement

Partial exits

Scaling out

Short trades

These belong to later phases.

ACCEPTANCE CRITERIA

Run system and verify:

Trades persist across ticks

Price breaches trigger exits

Time exits still override price exits

Strategy exits still work after MIN_HOLD_TICKS

Replay invariants remain OK

COMPLETION STATEMENT

This step is complete when:

Stop-loss exits function

Take-profit exits function

Exit ordering is correct

Trade lifecycle is fully engine-governed

END OF STEP 10.5


---

When Codex finishes, paste the output and we’ll **verify exit precedence and lifecycle integrity**.

Next after this will be:

👉 **Phase 10 · Step 10.6 — Multi-Condition Exit Precedence Validation**

You’re very close to a fully correct, production-grade lifecycle engine.
