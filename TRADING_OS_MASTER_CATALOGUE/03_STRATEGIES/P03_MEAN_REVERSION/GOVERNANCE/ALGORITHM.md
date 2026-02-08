# P03 — Mean Reversion — ALGORITHM (Canonical, Complete Coverage)
**Catalogue path:** `03_STRATEGIES/P03_MEAN_REVERSION/GOVERNANCE/ALGORITHM.md`  
**Timestamp:** 2026-02-08T01:01:41Z  
**Authority:** Trading OS Core E0–E21 + Metadata M0–M10 (LOCKED).  
**Rule of law:** **NO PARTIALS.** Every canonical registry item is classified for this strategy.

---

## 0) Strategy intent
P03_MEAN_REVERSION seeks **reversion toward a defined mean** after statistically/structurally confirmed overextension and continuation failure.

**Core premise:** When price becomes abnormally extended away from VWAP/EMA/value and shows exhaustion + failure to continue, mean reversion entries can offer favourable asymmetry.

---

## 1) Inputs / Outputs

### Inputs (from OS via StrategyContext)
- Market/session state, data quality flags, reference prices (E4)
- Price/volume features: distance to VWAP/EMAs, ATR, z-score/extension (E9)
- Structure: levels/zones, OR range, session range, key levels (E18/E20)
- Candle primitives + SCP/MCP detections (E18/E20)
- Regime flags (E8): trend vs range regime, volatility regime
- Risk/permission flags (E3/E10/E16)

### Outputs
- `TradeIntent` with trace fields:
  - `setup_family_id (SF_*)`
  - `execution_trigger_id (XL_*)`
  - evaluated `C_*` + failures
  - evaluated `K_*` + failures
  - invalidation (`INV_*`) defined
  - rationale with extension/mean metrics snapshot

---

## 2) Modes / timeframes (M3)
Default:
- Structure: 5MIN + 1MIN
- Execution: 1MIN (OPENING/MIDDAY/LATE), optional 10SEC only after certification

Mean reversion is **most fragile at the open**; OPENING mode must be stricter or may be disabled by policy.

---

## 3) Stock Selection (eligibility layer)
Mean reversion does not need “top gainers” only. It needs:
- liquid tradable symbols
- clear mean anchor (VWAP/EMAs/value zone)
- measurable extension (ATR multiples / z-score)
- acceptable spread

Outputs: Watchlist K and Focus M, ranked by:
- extension magnitude (bounded by “not too parabolic”)
- clarity of mean and invalidation
- liquidity/spread
- regime permission (range/chop vs strong trend)

---

## 4) Canonical Conditions (C_*) — REQUIRED
**Market/Session**
- C_SESSION_PHASE_ALLOWED
- C_TIME_OF_DAY_ALLOWED
- C_HALT_STATE_ALLOWED
- C_SSR_STATE_ALLOWED

**Data Quality**
- C_DATA_QUALITY_OK
- C_REFERENCE_PRICE_VALID
- C_HAS_BID_ASK
- C_STALE_DATA_REJECT
- C_SPREAD_WITHIN_LIMIT
- C_LIQUIDITY_WITHIN_MIN
- C_FLOAT_KNOWN_OR_ALLOWED

**Trend/Structure**
- C_LEVELS_BUILT_OK
- C_INVALIDATION_DEFINED
- C_SETUP_FAMILY_ACTIVE

**Volatility/Range**
- C_VOLATILITY_STATE_ALLOWED
- C_ATR_WITHIN_BOUNDS
- C_MEAN_DISTANCE_EXTREME (required for entry; defined by policy threshold)

**Volume/Participation**
- C_ABSOLUTE_VOLUME_OK

**Risk/Permission**
- C_RISK_ENGINE_APPROVED
- C_STRATEGY_PERMISSION_OK
- C_NO_TRADE_CONTEXT_FALSE
- C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED
- C_SYMBOL_COOLDOWN_EXPIRED

---

## 5) Canonical Confirmations (K_*) — REQUIRED vs OPTIONAL

### REQUIRED (always)
- K_DATA_QUALITY_CONFIRM
- K_SPREAD_CONFIRM
- K_LIQUIDITY_CONFIRM
- K_INVALIDATION_PRESENT_CONFIRM
- K_RISK_ENGINE_GREEN_CONFIRM

### REQUIRED (mean-reversion-specific)
- K_VOLUME_CONFIRM (exhaustion/shift acceptable; policy-defined)
- K_NO_PARABOLIC_EXHAUSTION_CONFIRM (avoid chasing blow-off; paradoxically can be both a signal and a deny)
- K_LEVEL_HOLD_CONFIRM OR K_BREAK_AND_REJECT_CONFIRM equivalent (use canonical: K_LEVEL_HOLD_CONFIRM + SCP/MCP evidence)

### OPTIONAL
- K_RETEST_CONFIRM (mean reclaim / failure retest)
- K_MARKET_REGIME_CONFIRM (prefer range/mean regime)
- K_INDEX_TREND_CONFIRM / K_SECTOR_STRENGTH_CONFIRM (to avoid fading strong market momentum)
- K_TIME_OF_DAY_CONFIRM
- K_TAPE_STRENGTH_CONFIRM / L2 confirms if available
- K_VOLATILITY_WINDOW_CONFIRM

---

## 6) Setup Families (SF_*) — complete classification

### ALLOWED (P03 core)
- SF_MEAN_REVERSION_EXTENSION
- SF_MEAN_REVERSION_FAILURE
- SF_MEAN_REVERSION_BOUNCE (only if failure evidence exists; otherwise deny as “catching falling knife”)
- SF_VWAP_FADE
- SF_KEY_LEVEL_RECLAIM (as an entry structure back toward mean)
- SF_RANGE_BOUND_FADE (if present in canon: use closest, else keep as DENIED and map to SF_MEAN_REVERSION_EXTENSION)

### OPTIONAL (conditional; enable when detectors robust)
- SF_OPENING_RANGE_FAKEOUT (as a reversal/fade structure, not breakout)
- SF_FAILED_BREAKOUT / SF_FAILED_BREAKDOWN (as “continuation failure” evidence)
- SF_LIQUIDITY_SWEEP (as exhaustion/trap evidence)

### DENIED (out-of-scope for P03 baseline)
- All momentum continuation setups: SF_MICRO_PULLBACK, SF_FIRST_PULLBACK, SF_BULL_FLAG, SF_TIGHT_FLAG, SF_GAP_AND_GO, etc.
- Long-horizon setups: SF_LONG_TERM_*, SF_WEEKLY_*, SF_MACRO_*
- Event/halt-specific: SF_HALT_RESUME, SF_EVENT_* (until specialised handling)

---

## 7) Execution Triggers (XL_*) — utilisation (complete list)

### ALLOWED for P03
- 05_XL_VWAP_RECLAIM (key entry when reclaiming VWAP back toward mean)
- 06_XL_EMA_RECLAIM (reclaim EMA9/20/50 as mean proxies)
- 08_XL_RANGE_BREAK (used as *exit/stop* evidence if price breaks further against mean; not an entry trigger)
- 11_XL_LIQUIDITY_SWEEP_RECLAIM (OPTIONAL entry if sweep detectors are certified)

### OPTIONAL
- 02_XL_ORB_RETEST (if using opening fakeout fade structure)
- 12_XL_LIQUIDITY_SWEEP_RECLAIM (if present; otherwise ignore)

### DENIED as primary entries
- 01_XL_ORB_BREAK, 07_XL_HOD_BREAK, 03/04 flag triggers, 00 micro pullback, 09 ABCD, 10 measured move (momentum/trend continuation oriented)

---

## 8) Candlestick patterns (SCP_*, MCP_*) — utilisation

**Rule:** SCP/MCP never directly trigger entries; they are inputs to confirmations and setup activation.

### SCP_* used (minimum)
Indecision/exhaustion:
- SCP_DOJI, SCP_SPINNING_TOP, SCP_HIGH_WAVE
- SCP_EXHAUSTION_WICK, SCP_VOLUME_CLIMAX_CANDLE, SCP_PARABOLIC_EXHAUSTION
Reversal shape:
- SCP_HAMMER, SCP_BULLISH_REJECTION, SCP_LONG_LOWER_WICK
- SCP_SHOOTING_STAR, SCP_BEARISH_REJECTION, SCP_LONG_UPPER_WICK
Level interaction:
- SCP_VWAP_REJECTION, SCP_VWAP_HOLD
- SCP_LEVEL_REJECTION, SCP_LEVEL_HOLD
Atomic primitives: all required SCP_* ratios and close-location outputs.

### MCP_* used (minimum)
- MCP_BREAK_AND_FAIL (failed breakout/down)
- MCP_STOP_RUN_REVERSAL (optional if certified)
- MCP_PARABOLIC_EXHAUSTION, MCP_CLIMAX_TOP/BOTTOM
- MCP_MEAN_REVERSION_SEQUENCE
- MCP_SUPPORT_RESISTANCE_FLIP (reclaim/flip)
- MCP_OPENING_FAKEOUT_SEQUENCE (optional)

---

## 9) Levels/Zones/Invalidations (required)
Mean anchors:
- LVL_VWAP, LVL_EMA_9, LVL_EMA_20, (optional) LVL_EMA_50
- ZONE_BALANCE_AREA / ZONE_CONSOLIDATION (if available)
Static:
- LVL_HIGH_OF_DAY / LOW_OF_DAY (for context/limits)
- ZONE_SESSION_RANGE

Invalidations (must be defined pre-entry):
- INV_VWAP_LOSS (for VWAP reclaim entries)
- INV_LEVEL_LOSS (for key level reclaims)
- INV_RANGE_FAILURE (if mean fails and range expands against you)
- INV_PATTERN_FAILURE (reversal pattern invalidated)

---

## 10) Entry templates (SF + XL)

### Template A — Extension + VWAP reclaim (SF_MEAN_REVERSION_EXTENSION + XL_VWAP_RECLAIM)
Preconditions:
- C_MEAN_DISTANCE_EXTREME true (policy threshold: e.g., distance >= X*ATR or zscore >= X)
- Evidence of exhaustion/continuation failure (MCP_BREAK_AND_FAIL or SCP_EXHAUSTION)
Confirmations:
- REQUIRED K_* plus K_LEVEL_HOLD_CONFIRM (mean hold) or K_RETEST_CONFIRM
Trigger:
- XL_VWAP_RECLAIM fires on reclaim of VWAP (per primitive)
Invalidation:
- INV_VWAP_LOSS

### Template B — EMA reclaim (SF_KEY_LEVEL_RECLAIM + XL_EMA_RECLAIM)
Used when VWAP not available/meaningful or EMA is the primary mean proxy.
Invalidation:
- INV_LEVEL_LOSS / INV_STRUCTURE_BREAK

### Template C — Liquidity sweep reclaim (SF_LIQUIDITY_SWEEP + XL_LIQUIDITY_SWEEP_RECLAIM) [OPTIONAL]
Only enabled after detector certification.
Invalidation:
- INV_PATTERN_FAILURE + INV_LEVEL_LOSS

---

## 11) Exits / stand-down (high-level)
Exits are executed by OS lifecycle engine (E2) + risk engine (E3). Strategy provides:
- invalidation definitions
- optional scale-out targets (mean, mid, VWAP, prior support)
- stop-tightening rules after reclaim confirmation
Stand-down:
- consecutive loss limit reached
- regime disallowed (strong trend day vs fade)
- data quality degradation

---

## 12) Completeness standard
Complete when:
- All relevant SF/XL/C/K/SCP/MCP/LVL/ZONES/INV are fully classified and mapped
- Policy exposes all tunable thresholds
- E21 verification proves parity across SIM/PAPER/READ_ONLY/LIVE.

