# ROSS_MOMENTUM_EXECUTION_SPEC.md

**Audience:** humans + machines. This is the “extensible spec” you requested: it mirrors the constitution but embeds **code-aligned** rules and variable names used by `strategy_policy.py` and `strategy_context_schema.py`.

## 0) Vocabulary (formal)
- **Ross Strategy Constitution**: immutable human contract (`CONSTITUTION.md`).
- **Ross Strategy Policy**: machine-readable rulebook (`strategy_policy.py`).
- **Ross Strategy Context**: live facts built by orchestrator (`strategy_context_schema.py`).
- **Ross Strategy Runner**: evaluates Policy × Context and emits intents (implemented elsewhere in the trading system).

## 1) Timeframes by function (Ross-aligned, automation-ready)
| Timeframe | Primary purpose |
|---|---|
| Daily | Stock selection, major S/R levels (50/200 SMA/EMA zones), “room to move” bias |
| 5-min | Setup validation, trend health, key level holds/breaks |
| 1-min | Entry structure, topping/reversal detection (wicks, stalls), manage exits |
| 10-sec | Execution precision: micro pullbacks / rapid re-entries |

### Session modes (one strategy, multiple modes)
We treat time-of-day execution speed as a **mode**, not a different strategy:
- **OPEN_FAST**: primary 10s execution; 1m used as safety monitor.
- **MIDDAY_SLOW**: same logic, but frequency reduced and thresholds tightened.
- **LATE_SLOW**: execution “shifts up” (commonly 1m behaves like 10s; 5m behaves like 1m) when volatility is lower.

(Exact mode boundaries live in `TRADE_PERMISSION_MATRIX.md` and are tunable policy parameters.)

## 2) Universal gates (must pass before any setup)
### In-play gate
Implemented by `is_in_play(sym, params)`.

**Automation-Ready Conditions**
```python
if not is_in_play(sym, p):
    reject("NOT_IN_PLAY")
```

Recommended minimums (tune in policy):
- `sym.premarket.gap_percent >= p.min_gap_percent`
- `sym.market.rel_volume >= p.min_rel_volume`
- Spread constraint: `(ask-bid)/last <= p.max_spread_pct`

### “No topping” safety gate
Ross exits early when the 1-minute candle begins to show topping behaviour.

**Automation-Ready Conditions**
```python
if should_stop_due_to_hard_reversal(sym, p):
    permission = "HALT"  # stop trading this symbol or session depending on policy
elif should_pause_due_to_topping(sym, p):
    permission = "PAUSE"  # manage existing; no adds
```

Notes:
- We use wick/body ratio because machines cannot “feel” discretion.
- This is where your 50% concept belongs: topping wick fraction.

## 3) Pattern: Micro Pullback (2–3 candles)
**Intent:** re-enter/add during a strong trend after a tiny, weak pullback.

### Definition (mechanically corrected)
- Pullback consists of **2–3 red candles** (10s in OPEN_FAST).
- Each red candle must be **small vs the impulse**.
- The pullback must not retrace too much of the impulse move.
- Volume on pullback must be **weak** vs impulse volume.
- Price must hold above support “floor” (VWAP/EMA9/EMA20) if available.

### Entry trigger (what you asked to verify)
We explicitly encode the trigger you described:
- After 2–3 red candles, **enter when price breaks above the high of the last red candle**.

**Automation-Ready Conditions**
```python
if micro_pullback_valid(sym, p):
    trigger = micro_pullback_entry_trigger(sym, p)  # last_red.high
    if sym.market.last is not None and trigger is not None and sym.market.last > trigger:
        emit_entry_intent("MICRO_PULLBACK", stop_model="STRUCTURE")
```

### Impulse definition (clarification)
For micro pullbacks we define the impulse as the most recent **dominant green candle** in the 10s window (see `micro_pullback_valid`).
- “Dominant” is approximated by the **largest green body** in the last N candles.
- Retrace is measured against impulse range; red candle “smallness” measured against impulse body.

### Exit / stand-down interaction
During micro pullback trading, the 1m chart remains the “safety override”:
- If a topping candle begins to form (wick/body above threshold), we **pause adds**.
- If a hard reversal candle forms, we **exit / stop trading**.

## 4) Pattern: First Pullback Continuation
(Primary execution on 1m; described in more detail in `SETUP_FAMILIES_AND_PATTERNS.md`.)

## 5) Level 2 (iceberg) integration (optional)
If L2 data is available, we treat it as **a filter and a fast-exit signal**, not a required dependency.
- Large persistent offer (“iceberg seller”) can force `PAUSE` or immediate `EXIT`.
- Large persistent bid can be an *allow* bias.

Schema support: `SymbolContext.l2_icebergs`.

## 6) MACD bias
If MACD is available, Ross-style bias is:
- Prefer trading when `macd > 0` (trend/momentum supportive).

Implemented as: `p.require_macd_positive`.

## 7) What remains to be implemented in code
This bundle defines constitution + policy + context schema. The remaining work is wiring:
- Orchestrator: build `StrategyContext` with required candles/indicators.
- Strategy Runner: evaluate policy rules, manage state (positions, adds, partials, trails).
- Execution: submit orders and update fills/positions.

## 1) Timeframes by function (mode-aware)
The policy is evaluated in a **mode** (see `StrategyContext.mode`). Each mode remaps “impulse” and “execution” timeframes.

| Mode | Typical U.S. session | Impulse / structure | Execution | Notes |
|---|---|---|---|---|
| `OPEN_FAST` | open -> first ~60–90m | M1 (structure) + S10 (micro) | S10 | fastest loop; most re-entries |
| `MIDDAY_SLOW` | late morning -> mid-afternoon | M5 + M1 | M1 | fewer opportunities; expect chop |
| `LATE_SLOW` | last ~90m | M5 (impulse) | M1 | “10s becomes 1m” style |

Policy requirement: the orchestrator must set `context.mode` deterministically from time-of-day or market volatility regime.

## 2) Pattern: Micro Pullback (2–3 red candles)
### Intent
Re-enter/add into an uptrend after weak selling.

### Preconditions
- `micro_pullback_valid(sym, p) == True`
- Trend already established (context has prior impulse; do not treat this as a first-entry pattern).

### Mechanical correction (automation)
Humans judge “weak” visually. The bot must quantify “weak”:
- **Body weakness:** each red body must be small vs impulse body.
- **Retrace weakness:** pullback low must not retrace too much of impulse range.
- **Volume weakness:** average red volume must be materially smaller vs impulse volume.

### Automation-Ready Conditions (code-aligned)
```python
from strategies.ross_momentum.strategy_policy import micro_pullback_valid, micro_pullback_entry_trigger, ROSS_POLICY

p = ROSS_POLICY.params

valid = micro_pullback_valid(sym, p)
trigger_price = micro_pullback_entry_trigger(sym, p)  # default: break last red high
```

#### Thresholds (RossPolicyParams)
- `micro_pullback_red_count in {2,3}`
- `micro_max_red_body_fraction_of_impulse = 0.30`  (each red body <= 30% of impulse body)
- `micro_max_total_pullback_retrace_of_impulse = 0.50` (pullback <= 50% retrace)
- `micro_max_red_volume_fraction_of_impulse = 0.40` (avg red vol <= 40% of impulse vol)
- `must_hold_above = ["VWAP", "EMA9", "EMA20"]`

### Entry trigger (clarified)
**Default (conservative):** enter on the first green candle that breaks above the **high of the most recent red candle** (the “last red”).
- Implementation: `trigger_price = last_red.high`.
- Execution: submit stop/marketable limit once price >= trigger.

If we later confirm Ross uses a different trigger (e.g., break of the pullback trendline or reclaim of a micro level), we switch `micro_entry_trigger` in policy.

### Invalidations
- Pullback breaks below VWAP/EMA floor (per `must_hold_above`).
- A red candle body exceeds `micro_max_red_body_fraction_of_impulse`.
- Total retrace exceeds 50% of the impulse range.
- In `OPEN_FAST`, a 1m topping candle appears (see section 4).

## 3) Confirmation bias: MACD + Volume
If indicators are present:
- **MACD:** require `sym.ind.macd > 0` (config: `require_macd_positive`).
- **Volume:** pullback red volume must be substantially smaller than impulse green volume (policy uses `micro_max_red_volume_fraction_of_impulse`).

## 4) Exit / stand-down: topping tails (1m)
Ross frequently avoids the top by reacting to topping behaviour on the 1m chart.

### Automation-Ready Conditions
```python
warn = should_pause_due_to_topping(sym, p)  # PAUSE new entries
stop = should_stop_due_to_hard_reversal(sym, p)  # HALT strategy for session
```
Thresholds:
- `topping_wick_fraction = 0.50` (warn)
- `hard_reversal_wick_fraction = 1.0` (halt)

Interpretation:
- **PAUSE:** no new entries; manage/exit open trades.
- **HALT:** flatten and stop trading for the day (requires manual reset in live mode).

## 5) Optional microstructure: Level 2 “iceberg”
If Level 2 data is available, the context can provide `sym.l2_icebergs`.
- Large persistent **ASK** iceberg near current price is a PAUSE/EXIT catalyst.
- Large persistent **BID** iceberg under price can support holds or re-entries.

This is optional; absence must not break the runner.
| `MIDDAY_SLOW` | midday | M5 (structure) + M1 (micro) | M1 | fewer trades; stricter permission |
| `LATE_SLOW` | late day | M5 (structure) + M1 (micro) | M1 | what Ross describes as “slower” |

**Important:** The system may run a single policy with mode remapping or separate policy variants per mode. In Track A we implement a *single policy* with explicit mode logic to avoid divergence.

## 2) Pattern: Micro Pullback (2–3 red candles)
This is the canonical “re-entry” loop pattern.

### Setup prerequisites
- `is_in_play(sym)` is true.
- Uptrend / momentum already confirmed at structure timeframe.
- Price holds above `VWAP/EMA9/EMA20` floor.

### Automation-ready conditions (policy-aligned)
In code, this is `micro_pullback_valid(sym, params)`.

```py
# key parameters (tunable)
params.micro_pullback_red_count = [2, 3]
params.micro_max_red_body_fraction_of_impulse = 0.30
params.micro_max_total_pullback_retrace_of_impulse = 0.50
params.micro_max_red_volume_fraction_of_impulse = 0.40
params.must_hold_above = ["VWAP", "EMA9", "EMA20"]
```

### Impulse definition (clarification)
For automation, “impulse” is the most recent strong green expansion bar inside a small window (`S10[-10:]` in our reference implementation). By default we use **body strength** to identify it, not just total range.

### Entry / re-entry trigger (double-checked logic)
We do **not** count “3rd or 4th green candle” as the trigger. The automation trigger is **price-based**, consistent with how discretionary traders act:
- After 2–3 red candles, enter on the first green candle that **breaks above the high of the last red candle**.

In policy:
```py
trigger = micro_pullback_entry_trigger(sym, params)
enter_if last_price >= trigger
```

### Topping-tail interaction (safety overlay)
Even if the 10s micro pattern is valid, the strategy must **pause new entries** if the latest M1 candle shows topping/reversal behaviour:
```py
pause = should_pause_due_to_topping(sym, params)
stop  = should_stop_due_to_hard_reversal(sym, params)
```

## 3) MACD and volume bias (verification behaviour)
Where MACD is available, entries prefer `macd > 0`. Where tape/volume shows dominant red (selling), the strategy pauses adds/re-entries.
## 2) Pattern: Micro Pullback (2–3 pullback candles)

### Definition
A controlled pullback against an established uptrend, characterised by **weak selling**.

### Automation correction (what “weak” becomes)
A machine cannot “feel” weakness; we translate it into constraints in `RossPolicyParams`:
- Each red candle body is small vs the **impulse candle body** (`micro_max_red_body_fraction_of_impulse`).
- The total retrace of the impulse range is limited (`micro_max_total_pullback_retrace_of_impulse`).
- Average red volume is limited vs impulse volume (`micro_max_red_volume_fraction_of_impulse`).
- Pullback low holds above VWAP/EMA9/EMA20 (where available) using `must_hold_above`.

### Impulse candle (formal)
For `OPEN_FAST` we define impulse on **S10** as the largest green body in the last N=10 candles (see `micro_pullback_valid`).
For slower modes, the same logic is applied on the execution timeframe (M1), but the impulse window can be widened.

### Entry trigger (your question: 3rd/4th green candle?)
We do **not** count “3rd vs 4th” green candles. The deterministic trigger is:
- Wait until the pullback produces 2–3 red candles.
- Enter on the **first green candle that breaks above the most recent pullback resistance**, which we operationalise as **the high of the last red candle**.

In code this is exported as:
```python
trigger = micro_pullback_entry_trigger(sym, p)  # returns last_red.high
```

### Automation-ready conditions
```text
IF in_play
AND trend == UP (via structure checks, runner)
AND micro_pullback_valid(sym, p)
AND last_price >= trigger_price (= last_red.high)
THEN enter/add (subject to trade permission)
```

### Exit / stop-new-entries guard (topping behaviour)
We implement Ross’s “I’m out before a topping tail / spinning top” as:
- `should_pause_due_to_topping`: last M1 candle wick/body >= `topping_wick_fraction` (default 0.50)
- `should_stop_due_to_hard_reversal`: wick/body >= `hard_reversal_wick_fraction` (default 1.00)

These are **permission-layer** checks: PAUSE blocks new entries; STOP triggers flatten/stand-down.
- Total retrace of impulse is limited (`micro_max_total_pullback_retrace_of_impulse`, default 0.50).
- Red volume is small vs impulse volume (`micro_max_red_volume_fraction_of_impulse`, default 0.40).
- Price holds above structure floors (VWAP/EMA9/EMA20) when available (`must_hold_above`).

### Impulse candle definition (explicit)
In `strategy_policy.py`, impulse is the **largest green body** in the last 10 S10 candles. This is a safe baseline for automation.

### Entry trigger (re-entry / add)
The conservative Ross-style trigger is:
- After 2–3 red candles, **enter on the first green candle that breaks above the high of the last red pullback candle**.

Code alignment:
```python
if micro_pullback_valid(sym, p):
    trigger = micro_pullback_entry_trigger(sym, p)  # last red high
    if sym.market.last and trigger and sym.market.last > trigger:
        signal = "ENTER"
```

### Exit/pauses while in the loop
- If the active M1 candle develops a long wick (“topping tail”), **pause new entries** and protect/exit.
- If wick becomes extreme (shooting-star style), **stop trading the ticker** (and possibly the session by permission matrix).

Code alignment:
```python
if should_pause_due_to_topping(sym, p):
    permission = "PAUSE"
if should_stop_due_to_hard_reversal(sym, p):
    permission = "DONE"
```
If you want a stricter definition later, replace with: “most recent breakout candle that created a new high.”

### Entry / re-entry trigger (your question)
Yes: the canonical automation trigger is:

```python
trigger_price = micro_pullback_entry_trigger(sym, p)
# default trigger is last red candle high
enter_when_last_price_crosses_above(trigger_price)
```

This corresponds to “first green candle breaks the high of the last red candle” in a 2–3-candle micro pullback. The policy implements `BREAK_LAST_RED_HIGH` as the first-pass, deterministic trigger.

### Invalidations
- Any pullback candle body exceeds `micro_max_red_body_fraction_of_impulse`.
- Pullback retrace exceeds 50% of impulse.
- Pullback low breaks below VWAP/EMA floors.
- MACD <= 0 when `require_macd_positive=True`.

### Automation-Ready Conditions
```
IF micro_pullback_valid(sym, params)
AND last_price > micro_pullback_entry_trigger(sym, params)
THEN signal = ENTER_OR_ADD
```
**Interpretation:**
- If pullback has 2 red candles, the *next* candle is the 3rd; entry when it breaks the last red high.
- If pullback has 3 red candles, the *next* candle is the 4th; entry when it breaks the last red high.

We do **not** enter merely because a green candle appears; we enter on the reclaim/ break.

### Automation-Ready Conditions
```
IF micro_pullback_valid(sym,p)
AND last_price > last_red_high
THEN entry_signal = TRUE
```

### Exit / pause overlays (topping)
Micro pullback trading is suppressed when the 1m candle shows topping risk:
```
IF should_pause_due_to_topping(sym,p) THEN no_new_entries
IF should_stop_due_to_hard_reversal(sym,p) THEN stop_trading_mode
```
