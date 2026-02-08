# P02 — Statistical Intraday Momentum — ALGORITHM (Canonical, Complete Coverage)
**Catalogue path:** `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM/GOVERNANCE/ALGORITHM.md`  
**Timestamp:** 2026-02-08T00:52:50Z  
**Authority:** Trading OS Core E0–E21 + Metadata M0–M10 (locked).  
**Rule of law:** **NO PARTIALS.** Every canonical registry item is **classified** as `ALLOWED / OPTIONAL / DENIED` for this strategy.  
**Execution law:** An entry intent may be emitted **iff**:
1) Eligible symbol from Stock Selection,
2) Required `C_*` conditions are true,
3) Required `K_*` confirmations pass,
4) A valid `SF_*` is active,
5) Exactly one `XL_*` trigger fires for that setup,
6) Invalidation (`INV_*`) is defined and present.

---

## 0) Strategy intent
**Statistical Intraday Momentum (SIMOM)** is a **data-driven, intraday continuation** strategy that seeks **positive expectancy breakouts/expansions** under statistically favourable regimes.

- Objective: rank intraday opportunities by expected continuation probability and favourable risk asymmetry.
- It is **not** Ross discretion; it is a **scored** strategy using OS analytics + regime layer + market state.

---

## 1) Inputs and outputs

### Inputs (from Trading OS)
- **Stock Selection outputs:** `EligibleSymbols`, `Watchlist K`, `Focus M`
- **StrategyContext** per symbol (built by orchestrator):
  - Market/session state, reference prices, data quality flags
  - Price/volume features (returns, ATR, RVOL, dollar volume, spread)
  - Levels/zones structures (HOD/LOD, OR, VWAP, EMAs, session range)
  - Regime/microstructure flags (E8)
  - Recent SCP_* and MCP_* detectors
  - Portfolio/risk engine permission flags (E3/E10/E16)

### Outputs
- `TradeIntent` objects (direction may be LONG-only initially; SHORT optional later)
- Required trace fields: `SF_*`, `XL_*`, key `C_*`, key `K_*`, rationale with metric snapshot IDs.

---

## 2) Modes and timeframes (M3 mode semantics)

**Mode** is derived from OS session phase. Strategy does not redefine market time semantics.

- **OPENING:** aggressive opportunity discovery; tighter data-quality requirements; avoid premature chasing unless confirmations are strong.
- **MIDDAY:** fewer trades, require stronger statistical edge.
- **LATE_DAY:** selective; avoid low-liquidity traps; prefer clean range expansions / power-hour behaviour.

Timeframes (default):
- Bias/Regime: DAILY + 15MIN
- Structure: 5MIN + 1MIN
- Execution: 10SEC (OPENING) / 1MIN (MIDDAY/LATE)

---

## 3) Stock Selection (eligibility layer; tunables in policy)
SIMOM uses a **mechanical eligibility filter**, then a **statistical ranking**.

### Eligibility gates (conceptual)
A symbol must pass:
- Data quality / reference price validity
- Liquidity/spread
- Sufficient volatility (ATR / range expansion presence) OR exceptional RVOL
- Session allowed (PRE/REG/AFTER as configured)

### Ranking (conceptual)
Rank_score may combine:
- z-scored intraday returns vs historical baseline (E9)
- RVOL + dollar volume
- Spread penalty
- Regime compatibility (E8)
- Proximity to triggerable levels (HOD/OR/VWAP reclaim)

Stock Selection outputs:
- `Watchlist K` (e.g., 15)
- `Focus M` (e.g., 3–5)

---

## 4) Canonical Conditions (C_*) — REQUIRED set
The following are **required** for any entry intent:

### Market/Session
- `C_TIME_OF_DAY_ALLOWED`
- `C_SESSION_PHASE_ALLOWED`
- `C_HALT_STATE_ALLOWED`
- `C_SSR_STATE_ALLOWED`

### Data Quality
- `C_DATA_QUALITY_OK`
- `C_REFERENCE_PRICE_VALID`
- `C_HAS_BID_ASK`
- `C_SPREAD_WITHIN_LIMIT`
- `C_LIQUIDITY_WITHIN_MIN`
- `C_STALE_DATA_REJECT`
- `C_FLOAT_KNOWN_OR_ALLOWED` (policy chooses allow/deny unknown)

### Trend/Structure
- `C_LEVELS_BUILT_OK`
- `C_INVALIDATION_DEFINED`
- `C_SETUP_FAMILY_ACTIVE`

### Volatility/Range
- `C_VOLATILITY_STATE_ALLOWED`
- `C_ATR_WITHIN_BOUNDS`

### Volume/Participation
- `C_RELATIVE_VOLUME_OK`
- `C_ABSOLUTE_VOLUME_OK`

### Risk/Permission
- `C_RISK_ENGINE_APPROVED`
- `C_STRATEGY_PERMISSION_OK`
- `C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED`
- `C_SYMBOL_COOLDOWN_EXPIRED`
- `C_NO_TRADE_CONTEXT_FALSE`

If any required condition fails → emit **no intent**, log decision artifact with failed C_* list.

---

## 5) Canonical Confirmations (K_*) — REQUIRED vs OPTIONAL

### REQUIRED confirmations (always)
- `K_DATA_QUALITY_CONFIRM`
- `K_SPREAD_CONFIRM`
- `K_LIQUIDITY_CONFIRM`
- `K_VOLUME_CONFIRM`
- `K_RELATIVE_VOLUME_CONFIRM`
- `K_INVALIDATION_PRESENT_CONFIRM`
- `K_RISK_ENGINE_GREEN_CONFIRM`

### OPTIONAL confirmations (strategy-selectable; used when available)
Market context:
- `K_MARKET_REGIME_CONFIRM`
- `K_INDEX_TREND_CONFIRM`
- `K_SECTOR_STRENGTH_CONFIRM`
- `K_TIME_OF_DAY_CONFIRM`
Volatility/tape:
- `K_VOLATILITY_WINDOW_CONFIRM`
- `K_TAPE_STRENGTH_CONFIRM` (if tape proxies exist)
- `K_L2_BID_STACK_CONFIRM` / `K_L2_ASK_THIN_CONFIRM` (if L2 enabled)
Structure:
- `K_BREAK_AND_HOLD_CONFIRM`
- `K_RETEST_CONFIRM`
- `K_LEVEL_HOLD_CONFIRM`
Risk:
- `K_NO_PARABOLIC_EXHAUSTION_CONFIRM`
- `K_NO_TOPPING_TAILS_CONFIRM`

Policy decides which OPTIONALs are enforced per SF_*, per mode.

---

## 6) Setup Families (SF_*) — Allowed / Optional / Denied

### ALLOWED (core SIMOM)
**Momentum/expansion**
- `SF_RANGE_EXPANSION`
- `SF_RANGE_FAILURE` (as *deny/reject* filter; not a long entry setup)
- `SF_VOLATILITY_EXPANSION`
- `SF_MOMENTUM_STAIRCASE`
**Gap/open structure (when aligned to statistical edge)**
- `SF_OPENING_RANGE_BREAKOUT`
- `SF_PREMARKET_HIGH_BREAK`
**Level-based**
- `SF_HIGH_OF_DAY_BREAK`
- `SF_KEY_LEVEL_BREAK`
- `SF_KEY_LEVEL_RECLAIM`
**Statistical/relative**
- `SF_RELATIVE_STRENGTH_LEADER`
- `SF_ZSCORE_EXTREME` (as *entry only if continuation edge exists*; otherwise deny)
**Time-of-day**
- `SF_POWER_HOUR_EXPANSION`

### OPTIONAL (future or conditional)
- `SF_VOLATILITY_CONTRACTION` (as precondition to expansion)
- `SF_COMPRESSION_COIL` / `SF_VOLATILITY_SQUEEZE` (if compression detectors are solid)
- `SF_OPENING_DRIVE` (if treated as a contextual label, not a separate strategy)
- `SF_EVENT_CONTINUATION` (if news/event feed is reliable)

### DENIED (out-of-scope for P02)
Mean reversion and fades:
- `SF_VWAP_FADE`, `SF_MEAN_REVERSION_*`, `SF_END_OF_DAY_REVERSION`
Reversal/trap primaries:
- `SF_STOP_RUN_REVERSAL`, `SF_BEAR_TRAP`, `SF_BULL_TRAP`, `SF_FAILED_BREAKOUT` (used only as *avoidance*)
Halt/event reversals:
- `SF_EVENT_REVERSAL`, `SF_HALT_RESUME` (until specialised handling is certified)
Long-horizon:
- `SF_LONG_TERM_*`, `SF_WEEKLY_*`, `SF_MACRO_*`

---

## 7) Execution Triggers (XL_*) — complete list + utilisation

**All canonical XL_* exist as primitives (E18).** This strategy uses:

### ALLOWED XL_* for P02
- `01_XL_ORB_BREAK` (for `SF_OPENING_RANGE_BREAKOUT`)
- `02_XL_ORB_RETEST` (optional; higher quality)
- `07_XL_HOD_BREAK` (for `SF_HIGH_OF_DAY_BREAK`)
- `08_XL_RANGE_BREAK` (for `SF_RANGE_EXPANSION`)
- `10_XL_MEASURED_MOVE` (for measured move continuations if modeled)
- `05_XL_VWAP_RECLAIM` (for `SF_KEY_LEVEL_RECLAIM` when level is VWAP)
- `06_XL_EMA_RECLAIM` (for pullback-based continuation if modeled)

### DENIED XL_* (not used as entries in P02 baseline)
- `00_XL_MICRO_PULLBACK` (Ross-style; belongs primarily to P01)
- `03_XL_FLAG_BREAK` / `04_XL_FLAG_RECLAIM` (optional later if flag detection is robust)
- `09_XL_ABCD` (optional later; only if ABCD modeling is added)
- `11_XL_LIQUIDITY_SWEEP_RECLAIM` (specialised; later)

---

## 8) Pattern utilisation (SCP_*, MCP_*) — complete classification approach

### SCP_* usage
SCP_* are **never direct triggers**. They feed confirmations like:
- `K_NO_TOPPING_TAILS_CONFIRM` (upper wick risk)
- `K_NO_PARABOLIC_EXHAUSTION_CONFIRM` (exhaustion candles)
- `K_BREAK_AND_HOLD_CONFIRM` (strong close location / marubozu)

SIMOM **uses** these as inputs:
- Momentum: `SCP_EXPANSION_CANDLE`, `SCP_STRONG_BULL_BODY`, `SCP_BULLISH_MARUBOZU`
- Exhaustion filters: `SCP_PARABOLIC_EXHAUSTION`, `SCP_VOLUME_CLIMAX_CANDLE`, `SCP_EXHAUSTION_WICK`
- Indecision filters: `SCP_DOJI`, `SCP_SPINNING_TOP`, `SCP_HIGH_WAVE`
- Level interaction: `SCP_LEVEL_HOLD`, `SCP_BREAK_AND_REJECT`, `SCP_LEVEL_REJECTION`
- Atomic primitives: all `SCP_*_X_PERCENT` outputs mandatory.

### MCP_* usage
MCP_* support SF activation and K confirmations:
- Expansion/break: `MCP_EXPANSION_SEQUENCE`, `MCP_RANGE_EXPANSION`, `MCP_BREAK_AND_HOLD`
- Opening: `MCP_OPENING_RANGE_SEQUENCE`
- Failure filters: `MCP_BREAK_AND_FAIL`, `MCP_FAILED_BREAKOUT`
- Optional: `MCP_COMPRESSION_COIL` / `MCP_NARROW_RANGE_SEQUENCE` before breakout

---

## 9) Levels/Zones/Invalidations
Required levels/zones for allowed setups:

- ORB: `ZONE_OPENING_RANGE`, `LVL_OPEN_PRICE`
- HOD: `LVL_HIGH_OF_DAY`
- VWAP: `LVL_VWAP` (and optionally `LVL_SESSION_VWAP`)
- Session range: `ZONE_SESSION_RANGE`, `ZONE_ROTATION_RANGE`
- Key level breaks: `ZONE_INTRADAY_RESISTANCE`, `ZONE_INTRADAY_SUPPORT`

Invalidations (must be defined pre-entry):
- `INV_LEVEL_LOSS` (breakout level reclaimed)
- `INV_RANGE_FAILURE`
- `INV_STRUCTURE_BREAK`
- `INV_PATTERN_FAILURE`

---

## 10) Entry decision templates (SF + XL)

### Template A — ORB Break (SF_OPENING_RANGE_BREAKOUT + XL_ORB_BREAK)
**Gate:** all required `C_*` true.  
**Confirm:** required `K_*`, plus `K_BREAK_AND_HOLD_CONFIRM` OR `K_TAPE_STRENGTH_CONFIRM`.  
**Trigger:** `01_XL_ORB_BREAK` fires when price breaks and holds above `ZONE_OPENING_RANGE` boundary per trigger primitive definition.  
**Invalidate:** `INV_LEVEL_LOSS` below OR high/low per direction.

### Template B — HOD Break (SF_HIGH_OF_DAY_BREAK + XL_HOD_BREAK)
Confirmations emphasise: `K_RELATIVE_VOLUME_CONFIRM`, `K_NO_PARABOLIC_EXHAUSTION_CONFIRM`.  
Trigger: `07_XL_HOD_BREAK`.  
Invalidation: loss of HOD level → `INV_LEVEL_LOSS`.

### Template C — Range Break (SF_RANGE_EXPANSION + XL_RANGE_BREAK)
Requires: `C_RANGE_EXPANSION_PRESENT` if available; otherwise MCP evidence.  
Trigger: `08_XL_RANGE_BREAK`.  
Invalidation: `INV_RANGE_FAILURE`.

---

## 11) Exit and stand-down (high-level)
Exit mechanics are governed by OS position lifecycle engine (E2) and risk engine (E3).
Strategy provides:
- Invalidation structures (INV_*)
- Optional trailing logic hints (e.g., trail under VWAP/EMA9; scale-out at measured move targets)
- Stand-down conditions: repeated losses; regime disallowed; data quality degradation.

---

## 12) What “complete” means here
This algorithm is “complete” when:
- Every canonical registry is **classified** and mapped for utilisation or explicit denial
- Strategy policy exposes every tunable knob
- Codex can implement missing pieces and verify via E21.

