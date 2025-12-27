# 37_PHASE_7_STEP_7_1_CODEX_INSTRUCTIONS_SIM_CLOCK_AND_ENTRY_PRICE.md

# PHASE 7 — TIME & PNL FOUNDATIONS
## STEP 7.1 — SIM CLOCK + DETERMINISTIC PRICE FEED + ENTRY METADATA

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce deterministic time and price awareness in SIM mode
and to record entry tick and entry price for each opened trade.

This step enables later PnL computation but MUST NOT calculate PnL yet.

Teaching-first. Deterministic. No randomness. No external data.

---

## OBJECTIVE

You will:

- Introduce a deterministic simulation clock
- Introduce a deterministic price feed
- Record entry tick and entry price when trades open
- Extend trade registry to store structured entry metadata
- Emit clear logs and events for teaching and replay

---

## FILES TO CREATE

Create the following new files:

- src/sim/clock.py
- src/sim/price_feed.py

---

## FILES TO MODIFY

Modify ONLY the following files:

- src/orchestrator/orchestrator.py
- src/core/active_trade_registry.py
- src/execution/execution_engine.py
- src/events/system_events.py (if TRADE_OPENED payload exists)

Do not modify any other files.

---

## STEP 1 — CREATE DETERMINISTIC SIM CLOCK

Create file:

src/sim/clock.py

Add the following code:

```python
class SimClock:
    """
    Deterministic simulation clock.
    Advances exactly one tick per orchestrator cycle.
    """

    def __init__(self, start_tick: int = 0):
        self._tick = start_tick

    def tick(self) -> int:
        self._tick += 1
        print(f"[CLOCK] tick={self._tick}")
        return self._tick

    def now(self) -> int:
        return self._tick
```

---

## STEP 2 — CREATE DETERMINISTIC PRICE FEED

Create file:

src/sim/price_feed.py

Add the following code:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PricePoint:
    symbol: str
    tick: int
    price: float


class DeterministicPriceFeed:
    """
    Teaching-only deterministic price generator.
    """

    BASE_PRICES = {
        "ABC": 12.35,
        "XYZ": 47.80,
        "LMN": 6.75,
        "QRS": 83.40,
    }

    INCREMENTS = {
        "ABC": 0.02,
        "LMN": 0.03,
        "XYZ": 0.01,
        "QRS": 0.00,
    }

    def price_for(self, symbol: str, tick: int) -> float:
        base = self.BASE_PRICES.get(symbol, 10.0)
        inc = self.INCREMENTS.get(symbol, 0.0)
        price = round(base + inc * tick, 2)
        print(f"[PRICE_FEED] symbol={symbol} tick={tick} price={price}")
        return price
```

---

## STEP 3 — INITIALISE CLOCK AND PRICE FEED IN ORCHESTRATOR

Modify:

src/orchestrator/orchestrator.py

During orchestrator initialisation:

- Create ONE SimClock instance
- Create ONE DeterministicPriceFeed instance
- Store them on self

Example requirement (do not copy blindly, adapt to structure):

```python
self.sim_clock = SimClock()
self.price_feed = DeterministicPriceFeed()
```

At the START of each run_once() cycle:

```python
tick = self.sim_clock.tick()
print(f"[CYCLE_CTX] tick={tick} run_mode={self.run_mode}")
```

This tick must be reused across the entire cycle.

---

## STEP 4 — EXTEND ACTIVE TRADE REGISTRY TO STORE ENTRY METADATA

Modify:

src/core/active_trade_registry.py

Introduce a structured ActiveTrade object:

```python
from dataclasses import dataclass

@dataclass
class ActiveTrade:
    symbol: str
    trader_type: str
    entry_tick: int
    entry_price: float
```

Update registry logic to:

- Store ActiveTrade objects (not dicts)
- Register trades via ActiveTrade
- Unregister by symbol + trader_type

Add logs:

```text
[REGISTRY] REGISTER symbol=ABC trader_type=SCALPER entry_tick=3 entry_price=12.41
[REGISTRY] UNREGISTER symbol=ABC trader_type=SCALPER
```

Registry remains in-memory only.

---

## STEP 5 — CAPTURE ENTRY TICK AND PRICE DURING EXECUTION

Modify:

src/execution/execution_engine.py

When a trade is allowed and opened in SIM mode:

1. Obtain current tick from orchestrator context
2. Obtain price via DeterministicPriceFeed
3. Create ActiveTrade instance
4. Register trade in ActiveTradeRegistry

Required behavior:

```python
entry_price = self.price_feed.price_for(symbol, tick)

active_trade = ActiveTrade(
    symbol=symbol,
    trader_type=trader_type,
    entry_tick=tick,
    entry_price=entry_price,
)

self.trade_registry.register_trade(active_trade)

print(
    f"[EXECUTION] OPEN symbol={symbol} "
    f"tick={tick} entry_price={entry_price} (SIM)"
)
```

---

## STEP 6 — EXTEND TRADE_OPENED EVENT PAYLOAD

When emitting TRADE_OPENED events, ensure payload includes:

- symbol
- trader_type
- entry_tick
- entry_price

Example log:

```text
[EVENT] TRADE_OPENED symbol=ABC trader_type=SCALPER tick=3 price=12.41
```

Do NOT calculate PnL yet.

---

## VALIDATION REQUIREMENTS

After implementation:

1. Tick increments deterministically per cycle
2. Price is deterministic across runs
3. Entry tick and price are stored for every trade
4. Registry contains structured ActiveTrade objects
5. Replay continues to work
6. No randomness, no external APIs
7. No PnL calculation yet

---

## COMPLETION CRITERIA

This step is complete when:

- Time is a first-class system concept
- Price is deterministic and reproducible
- Trades record when and at what price they entered
- System remains teaching-first and stable

---

## NEXT ACTION

Run the system.

When complete, respond with:

“PHASE 7 STEP 7.1 complete — ready for Step 7.2”
