# REPORT — “Reading Candlestick Charts Was HARD Until I Learned This 3 Step Trick”

**Source transcript:** `Reading Candlestick Charts Was HARD Until I Learned This 3 Step Trick.doc`

## 1) The 3-step evaluation loop (as expressed in the transcript)
1. **Locate context / key levels**: identify obvious support/resistance and prior swing highs/lows.
2. **Read the candle for control**: candle body vs wick to infer who is in control (buyers vs sellers).
3. **Confirm with volume**: volume validates the move; heavy volume into resistance is more credible than light volume.

## 2) Ross-relevant takeaways
### A) Wick-based reversal reading (topping behaviour)
- Long upper wicks after an advance indicate rejection and often precede pullbacks/reversals.

**Automation translation** (policy-aligned)
```python
wick_fraction = _candle_wick_fraction(last_m1_candle)
warning = wick_fraction >= p.topping_wick_fraction  # default 0.50
hard_stop = wick_fraction >= p.hard_reversal_wick_fraction  # default 1.0
```

### B) Volume confirms intent
- Breakouts should be accompanied by rising volume (or at least not collapsing volume).
- Red candles with unusually high volume indicate stronger selling pressure.

**Automation translation (micro pullback weakness)**
```python
avg_red_vol = mean(red.volume for red in pullback)
weak_selling = (avg_red_vol / impulse.volume) <= p.micro_max_red_volume_fraction_of_impulse
```

### C) Bias toward continuation only when structure is intact
- Candles must respect VWAP / moving averages for continuation setups; loss of these levels is an invalidation signal.

**Automation translation**
```python
pb_low >= max(vwap, ema9, ema20)  # when available
```

## 3) Integration notes
This transcript is primarily a **candle-reading / confirmation** lesson. It strengthens two Ross invariants we already encode:
- “Weak selling” equals *small bodies + limited retrace + limited red volume*.
- “Topping” equals *large wick fractions*, which trigger pause/exit rules.

## 2) Ross-specific operationalisations
### Volume
- Green volume expansion supports continuation; a single red candle on **heavy red volume** is treated as a degradation signal (pause or exit depending on position state).

**Automation-ready mapping**
```python
heavy_red = (red_candle.volume > prior_green.volume) and (red_candle.close < red_candle.open)
if heavy_red:
    permission_state = "PAUSE"  # no new adds; manage exit
```

### MACD bias
Ross’s transcript reiterates a preference for trading when momentum indicators are supportive.

**Automation-ready mapping** (already in policy)
```python
if policy.params.require_macd_positive and sym.ind.macd is not None:
    require(sym.ind.macd > 0)
```

### Candlestick warning: long wicks / indecision
Long upper wicks / shooting-star-like behaviour is treated as an early warning for topping. This is formalised as wick-to-body ratios in `strategy_policy.py`:
- `topping_wick_fraction` -> PAUSE
- `hard_reversal_wick_fraction` -> STOP TRADING for the session
