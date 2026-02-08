# P01_ROSS_MOMENTUM — ALGORITHM (Canonical, Complete Coverage)
Date: 2026-02-08
Status: AUTHORITATIVE SPEC (E18–E21 + M0–M10 aligned)

## Purpose
Ross Momentum is a **small-cap momentum** strategy that:
- selects **in-play gappers / top gainers** with **low float + high RVOL + catalyst**
- trades **continuations** (HOD/ORB/flags/pullbacks) and **reclaims** (VWAP/EMA/levels)
- uses **fast execution at the open** and slows cadence later via **mode presets**

This algorithm is **deterministic** and **compositional**:
- **Structure** is expressed as Setup Families (**SF_***)
- **Permission** is expressed as Conditions (**C_***)
- **Evidence** is expressed as Confirmations (**K_***)
- **Entries** are expressed as Execution Triggers (**XL_***)
- **Candle patterns** (SCP_*, MCP_*) are *inputs* to confirmations/filters, never direct entries.

---

## 0) Strategy Inputs / Outputs

### Inputs
- Stock-selection observations (`CandidateMetrics` or equivalent) from OS eligibility layer
- StrategyContext for each symbol including:
  - market/session state, data quality, spreads/liquidity, halt/SSR flags
  - levels/zones (VWAP, EMA9/20/50, PMH/PML, ORB, HOD/LOD, PDH/PDL, etc.)
  - candle streams for required timeframes per mode
  - computed indicators (VWAP, EMAs, optional MACD) and pattern primitives (SCP/MCP outputs)
  - risk/permission status from OS (max losses, cooldowns, etc.)

### Output
- TradeIntents with full traceability:
  - `setup_family_id` (SF_*)
  - `execution_trigger_id` (XL_*)
  - gating snapshot: required C_* and K_* pass/fail results
  - rationale including numeric parameter values used

---

## 1) Mode semantics (M3) and timeframe plan
Ross trades with mode presets (one strategy, multiple cadences):

**Mode → Timeframes**
- OPENING_DRIVE: bias=DAILY, setup=5MIN, structure=1MIN, execution=10SEC
- MIDDAY:        bias=DAILY, setup=5MIN, structure=1MIN, execution=10SEC (reduced aggression via parameters)
- LATE_DAY:      bias=DAILY, setup=15MIN, structure=5MIN, execution=1MIN

The OS sets `context.session_phase` and strategy maps to `RossTradingMode`.
All time boundaries are **policy parameters** (never hard-coded).

---

## 2) Stock Selection (Eligibility Layer, not setups)
Ross stock selection uses the **5 pillars** (price, gap/%change, RVOL, float, catalyst) plus tradability gates.
Key published thresholds include RVOL>=5 and “already up ~10%” as a baseline. citeturn0search9turn0search5

### Eligibility pipeline
1. **Universe**: IBKR Top % Gainers / configured symbols
2. **Hard gates** (drop if fail):
   - session allowed (PRE/REG/AFTER) and market state valid
   - data quality minimal (price present; optional bid/ask)
   - liquidity minimums (volume, $ volume) and spread max
   - exclusions (OTC, stale, non-tradable, subscription gaps)
3. **Ross pillars** (rank / filter):
   - price range (tunable)
   - % gap / % change (tunable)
   - RVOL min (tunable; baseline 5x) citeturn0search9
   - float max (tunable; baseline <=20M ideal) citeturn0search5turn0search17
   - catalyst required (tunable; baseline True)
4. **Rank** and cut:
   - Watchlist K (default 15)
   - Focus M (default 3–5)

**Important:** session-aware reference price semantics are OS-owned (E4/E6). Strategy only consumes `pct_change`/`gap_pct` plus provenance.

---

## 3) Canonical Setup Families used by Ross (complete, explicit)
Ross Momentum may use the following SF_* as **ALLOWED** (everything else is explicitly DENIED for Ross).

### A) Gap & Open Structure
- SF_GAP_AND_GO
- SF_OPENING_RANGE_BREAKOUT
- SF_OPENING_RANGE_FAKEOUT
- SF_PREMARKET_HIGH_BREAK
- SF_PREMARKET_LOW_BREAK (short-biased later; for v1 LONG-only treat as DENIED unless enabled)

### B) Momentum Continuation
- SF_FIRST_PULLBACK
- SF_SECOND_PULLBACK (optional / later)
- SF_MICRO_PULLBACK
- SF_BULL_FLAG
- SF_TIGHT_FLAG
- SF_FLAT_TOP_BREAKOUT
- SF_ASCENDING_TRIANGLE
- SF_MOMENTUM_STAIRCASE (optional)
- SF_PARABOLIC_CONTINUATION (allowed but guarded; often becomes NO-TRADE under exhaustion)

### C) Level-Based Structure
- SF_HIGH_OF_DAY_BREAK
- SF_KEY_LEVEL_RECLAIM
- SF_KEY_LEVEL_BREAK (optional)
- SF_PRIOR_DAY_HIGH_BREAK (optional)
- SF_PRIOR_DAY_CLOSE_RECLAIM (optional)

### D) VWAP & Mean Structure (Ross uses VWAP reclaims; fades are typically discretionary/advanced)
- SF_VWAP_RECLAIM
- SF_VWAP_TREND_DAY (context/bias)
- SF_VWAP_FADE (DENIED by default in Ross v1 unless explicitly enabled)

### E) Halt, News & Event
- SF_HALT_RESUME (allowed only if policy allows halts)
- SF_NEWS_SPIKE
- SF_EARNINGS_REACTION (optional; most Ross trades are news-driven but earnings reactions are a specific subset)
- SF_EVENT_CONTINUATION

### F) Time-of-day Structure (used as *context overlays*, not separate strategies)
- SF_OPENING_DRIVE
- SF_MIDDAY_COMPRESSION
- SF_POWER_HOUR_EXPANSION

**DENIED (examples):** mean-reversion setups, pairs, long-horizon, range-bound fade (unless explicitly enabled in a different strategy).

---

## 4) Canonical Execution Triggers (E18) and mapping (complete)
Triggers are reusable primitives and do not decide permission.

For each allowed setup family, Ross arms one or more XL_*:

- 00_XL_MICRO_PULLBACK → SF_MICRO_PULLBACK
- 01_XL_ORB_BREAK → SF_OPENING_RANGE_BREAKOUT
- 02_XL_ORB_RETEST → SF_OPENING_RANGE_BREAKOUT
- 03_XL_FLAG_BREAK → SF_BULL_FLAG, SF_TIGHT_FLAG, SF_FLAT_TOP_BREAKOUT, SF_ASCENDING_TRIANGLE
- 04_XL_FLAG_RECLAIM → SF_BULL_FLAG (failed-break reclaim)
- 05_XL_VWAP_RECLAIM → SF_VWAP_RECLAIM
- 06_XL_EMA_RECLAIM → SF_FIRST_PULLBACK / SF_SECOND_PULLBACK (reclaim of EMA9/EMA20)
- 07_XL_HOD_BREAK → SF_HIGH_OF_DAY_BREAK
- 08_XL_RANGE_BREAK → SF_MOMENTUM_STAIRCASE / SF_RANGE_EXPANSION (if enabled)
- 09_XL_ABCD → SF_ABCD_CONTINUATION (optional; Ross uses “ABCD / measured move” language)
- 10_XL_MEASURED_MOVE → SF_ABCD_CONTINUATION / projections (optional)
- 11_XL_LIQUIDITY_SWEEP_RECLAIM → SF_LIQUIDITY_SWEEP (optional for Ross; typically advanced)

---

## 5) Conditions (C_*) — required gates before any setup/triggers
Minimum required conditions for *any* entry intent:

### Market/Session
- C_SESSION_PHASE_ALLOWED
- C_HALT_STATE_ALLOWED
- C_SSR_STATE_ALLOWED

### Data Quality / Tradability
- C_DATA_QUALITY_OK
- C_REFERENCE_PRICE_VALID
- C_HAS_BID_ASK (optional in sim; required in live if using spread gating)
- C_SPREAD_WITHIN_LIMIT
- C_LIQUIDITY_WITHIN_MIN
- C_STALE_DATA_REJECT
- C_FLOAT_KNOWN_OR_ALLOWED

### Risk/Permission
- C_RISK_ENGINE_APPROVED
- C_STRATEGY_PERMISSION_OK
- C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED
- C_SYMBOL_COOLDOWN_EXPIRED
- C_NO_TRADE_CONTEXT_FALSE

### Structure/Setup activation
- C_SETUP_FAMILY_ACTIVE
- C_INVALIDATION_DEFINED

---

## 6) Confirmations (K_*) — required evidence set
### Required (common baseline)
- K_DATA_QUALITY_CONFIRM
- K_SPREAD_CONFIRM
- K_LIQUIDITY_CONFIRM
- K_RELATIVE_VOLUME_CONFIRM
- K_VOLUME_CONFIRM
- K_INVALIDATION_PRESENT_CONFIRM
- K_RISK_ENGINE_GREEN_CONFIRM

### Setup-dependent required confirmations
- K_BREAK_AND_HOLD_CONFIRM (ORB / flag breakouts)
- K_RETEST_CONFIRM (ORB retest / flag reclaim)
- K_LEVEL_HOLD_CONFIRM (VWAP/EMA/level holds)
- K_PULLBACK_WEAK_VOLUME_CONFIRM (micro/first pullback)
- K_NO_TOPPING_TAILS_CONFIRM (topping risk overlay)
- K_NO_PARABOLIC_EXHAUSTION_CONFIRM (parabolic guard)

### Optional confirmations (policy-selectable)
- K_TAPE_STRENGTH_CONFIRM
- K_L2_BID_STACK_CONFIRM / K_L2_ASK_THIN_CONFIRM
- K_SECTOR_STRENGTH_CONFIRM / K_INDEX_TREND_CONFIRM
- K_NEWS_CATALYST_CONFIRM
- K_TIME_OF_DAY_CONFIRM
- K_MARKET_REGIME_CONFIRM
- K_VOLATILITY_WINDOW_CONFIRM
- K_HALT_RESUME_STABILITY_CONFIRM

---

## 7) Candlestick and sequence primitives (SCP_*, MCP_*) — usage mapping
Candlestick registries are **fully available**; Ross uses a subset as explicit filters/telemetry.

### Used SCP_* (examples; complete list remains available)
**Indecision / topping filters**
- SCP_DOJI, SCP_SPINNING_TOP, SCP_HIGH_WAVE
- SCP_GRAVESTONE_DOJI (topping risk), SCP_LONG_UPPER_WICK

**Momentum validation**
- SCP_STRONG_BULL_BODY, SCP_EXPANSION_CANDLE, SCP_BULLISH_MARUBOZU (telemetry)

**Reversal warnings**
- SCP_SHOOTING_STAR, SCP_HANGING_MAN, SCP_BEARISH_REJECTION
- SCP_PARABOLIC_EXHAUSTION, SCP_VOLUME_CLIMAX_CANDLE

### Used MCP_* (setup detectors)
- MCP_MICRO_PULLBACK_2, MCP_MICRO_PULLBACK_3
- MCP_FIRST_PULLBACK
- MCP_BULL_FLAG, MCP_TIGHT_FLAG, MCP_FLAT_TOP
- MCP_OPENING_RANGE_SEQUENCE, MCP_BREAK_AND_HOLD, MCP_LEVEL_RECLAIM_SEQUENCE
- MCP_PARABOLIC_EXHAUSTION (guard), MCP_CLIMAX_TOP (guard)
- MCP_GAP_AND_GO_SEQUENCE (gap-and-go context)

---

## 8) Entries — deterministic intent emission
For each symbol in Focus M, for each ALLOWED SF_* that is active:

1. Evaluate required C_* (hard gates). If any fail → NO TRADE.
2. Evaluate required K_* confirmations for that SF_*. If any fail → NO TRADE.
3. Arm the mapped XL_* trigger(s). If trigger fires → emit TradeIntent.

**Intent fields (must include):**
- SF id, XL id
- entry price reference and trigger price
- invalidation reference (INV_* + numeric stop reference)
- mode, timeframe plan
- confidence model based on confirmations (no opaque “strength”)

---

## 9) Exits / stand-down (policy-controlled; OS-owned execution/lifecycle)
Ross uses:
- structure invalidation: break of pullback low / VWAP loss / level loss (INV_*)
- topping risk: PAUSE adds; HALT new entries when confirmed reversal (ToppingRiskSpec)
- time stop: optional “if no follow-through”
- profit management: partials + trail (OS position lifecycle; strategy defines intent-level preferences)

This algorithm only specifies **signals for exit intents**; execution and position management are OS-owned (E2/E5).

---

## 10) Completeness rule (NO PARTIALS)
For certification, every canonical registry item must be classified as:
- ALLOWED (implemented)
- OPTIONAL (implemented but disabled by default)
- DENIED (explicitly out of scope for Ross)

No “missing / unknown” allowed for LIVE.

END
