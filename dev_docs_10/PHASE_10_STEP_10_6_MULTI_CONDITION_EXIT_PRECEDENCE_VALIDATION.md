📄 PHASE_10_STEP_10_6_MULTI_CONDITION_EXIT_PRECEDENCE_VALIDATION.md
# PHASE 10 — REAL TRADE LIFECYCLES
## STEP 10.6 — MULTI-CONDITION EXIT PRECEDENCE VALIDATION (TESTS + INVARIANTS)

### OBJECTIVE

Prove (with deterministic, replay-safe validation) that **exit precedence** is correct when multiple exit conditions are simultaneously eligible.

This step adds:
- A dedicated precedence matrix
- Deterministic scenario tests (engine-level)
- Invariant checks ensuring ONLY the highest-priority exit fires

No new trading logic beyond validation.
No new features.
This is correctness hardening.

---

### EXIT PRECEDENCE (AUTHORITATIVE ORDER)

TradeExitEngine MUST enforce the following priority order:

1. **MAX_HOLD_TICKS reached** → FORCE EXIT (TIME_MAX)
2. **STOP_LOSS breached** → FORCE EXIT (PRICE_STOP)
3. **TAKE_PROFIT reached** → FORCE EXIT (PRICE_TP)
4. **MIN_HOLD_TICKS not reached** → BLOCK STRATEGY exits (TIME_MIN_BLOCK)
5. **Strategy ExitSignal present** → EXIT (STRATEGY_SIGNAL)
6. Else → HOLD

This order must be validated with tests.

---

### VALIDATION STRATEGY

We will validate precedence at the **TradeExitEngine boundary**, using deterministic inputs:
- Known entry_tick
- Known tick (current)
- Known entry_price
- Known current_price
- Known min_hold_ticks / max_hold_ticks
- Known stop_loss_price / take_profit_price
- Known (fake) strategy exit signal availability

We do NOT need a full orchestrator run for precedence validation.
We test the engine directly.

---

### NEW FILES TO ADD

Create a minimal deterministic test harness (no third-party libs required).

1) `src/tests/__init__.py`
2) `src/tests/test_exit_precedence.py`

If your repo already has a tests folder, re-use it but follow the same file names.

---

### REQUIRED SMALL REFACTOR (IF NEEDED)

If TradeExitEngine currently mixes “compute decision” and “apply close” in one method,
introduce a pure function method for testing:

File: `src/core/trade_exit_engine.py`

Add method:

```python
def decide_exit(
    self,
    trade: ActiveTrade,
    tick: int,
    current_price: float,
    strategy_exit_signal: bool,
    config: RuntimeConfig,
) -> ExitDecision | None:
    ...

Where:


returns ExitDecision if an exit should happen


returns None if HOLD


ExitDecision must include:


reason (string)


category (enum or string: TIME_MAX / PRICE_STOP / PRICE_TP / STRATEGY_SIGNAL)


exit_tick


exit_price


TradeExitEngine’s normal run path MUST use this same method internally, ensuring test alignment.

EXIT DECISION MODEL
File (new or existing): src/core/exit_decision.py
If you do not already have one, create:
from dataclasses import dataclass

@dataclass(frozen=True)
class ExitDecision:
    symbol: str
    trader_type: str
    strategy_name: str
    category: str
    reason: str
    exit_tick: int
    exit_price: float


TEST MATRIX (MUST IMPLEMENT)
File: src/tests/test_exit_precedence.py
Create deterministic unit-style tests using plain Python assert.
You MUST cover these scenarios:
CASE A — MAX HOLD overrides everything
Given:


tick - entry_tick >= max_hold_ticks


stop_loss breached


take_profit reached


strategy_exit_signal=True


Expected:


category == TIME_MAX


reason contains "Max hold"


no other exit categories fire


CASE B — STOP LOSS overrides take profit + strategy
Given:


max_hold NOT reached


stop_loss breached


take_profit reached


strategy_exit_signal=True


min_hold satisfied


Expected:


category == PRICE_STOP


CASE C — TAKE PROFIT overrides strategy
Given:


max_hold NOT reached


stop_loss NOT breached


take_profit reached


strategy_exit_signal=True


min_hold satisfied


Expected:


category == PRICE_TP


CASE D — MIN HOLD blocks strategy but not forced exits
Given:


min_hold NOT satisfied


strategy_exit_signal=True


stop_loss NOT breached


take_profit NOT reached


max_hold NOT reached


Expected:


decision is None (HOLD)


no exit


CASE E — MIN HOLD does NOT block stop loss
Given:


min_hold NOT satisfied


stop_loss breached


strategy_exit_signal=True


Expected:


category == PRICE_STOP


CASE F — Strategy exit allowed only after MIN HOLD
Given:


min_hold satisfied


strategy_exit_signal=True


no price breaches


max_hold NOT reached


Expected:


category == STRATEGY_SIGNAL


CASE G — No conditions → HOLD
Given:


no time trigger


no price trigger


strategy_exit_signal=False


Expected:


decision is None



TEST FIXTURES
Create helper functions inside the test file:


make_trade(...) returning an ActiveTrade instance


Provide deterministic defaults


Use LONG only


If ActiveTrade class is not directly importable, create a minimal stub matching fields used in decision logic.

REQUIRED LOGGING FOR VALIDATION
When decide_exit returns a decision:
[EXIT][DECISION] symbol=ABC category=PRICE_STOP tick=5 price=12.10 reason="Stop-loss price breached"

Tests do not assert logs; logs are for humans.

REPLAY INVARIANT (MUST REMAIN TRUE)
This step MUST NOT change replay behaviour.
Replay is still:


Based on events


Not re-evaluating exit rules


Validation code must not affect production logic except via refactor into decide_exit.

ACCEPTANCE CRITERIA
This step is complete when:


All test cases A–G pass


TradeExitEngine uses decide_exit internally


Precedence order is enforced exactly


No behaviour regressions in normal SIM runs


Replay invariants still show OK



COMPLETION STATEMENT
Step 10.6 is complete when the exit precedence matrix is validated by deterministic tests and the TradeExitEngine’s behaviour is provably consistent across all multi-condition scenarios.
END OF STEP 10.6
::contentReference[oaicite:0]{index=0}
