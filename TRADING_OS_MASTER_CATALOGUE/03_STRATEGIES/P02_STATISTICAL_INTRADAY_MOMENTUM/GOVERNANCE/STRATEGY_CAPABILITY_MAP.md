# P02 — Statistical Intraday Momentum — STRATEGY CAPABILITY MAP (Complete, No Partials)
**Catalogue path:** `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM/GOVERNANCE/STRATEGY_CAPABILITY_MAP.md`  
**Timestamp:** 2026-02-08T00:52:50Z

## 0) Purpose
This document binds P02 to the Trading OS canon. It is **exhaustive**:
- All canonical registries are classified (`ALLOWED / OPTIONAL / DENIED`)
- Utilisation is explicitly mapped (where used)
- No implicit behaviour is allowed in LIVE certification.

---

## 1) Required OS capabilities (by epoch)
- E4 Data Quality + Market State: reference prices, stale data detection, bid/ask availability
- E6 Scanner ↔ Strategy Contract: CandidateMetrics, gate_checks, session labeling
- E7 Mode parity: SIM/PAPER/READ_ONLY/LIVE behaviour parity
- E8 Regime layer: regime flags + microstructure
- E9 Analytics: z-scores, baselines, ranking support
- E10 Allocation: capital caps, per-strategy allocation
- E14 Decision artifacts: full traceability for every decision
- E16 No-trade contexts: enforce “no-trade” conditions
- E18 Trigger primitives XL_* exist and are reusable
- E19 Strategy interface/certification: required artifacts
- E21 End-to-end simulation: scan→watchlist→focus→intent→execution→DB.

---

## 2) Stock Selection ownership
**Authority:** Strategy policy owns tunables; scanner provides raw candidates + telemetry only.

### Inputs (CandidateMetrics minimum)
- symbol, pct_change, gap_percent, rvol, dollar_volume, spread_pct
- session_label, gate_checks, drop_reasons
- (optional) float_millions, catalyst flags, halts/SSR flags

### Outputs
- watchlist K
- focus M

---

## 3) Canon registries: utilisation tables

### 3.1 Execution Triggers (XL_*) — complete list
| XL ID | Status | Used for SF | Notes |
|---|---|---|---|
| 00_XL_MICRO_PULLBACK | DENIED | — | Ross-style; P01 primary |
| 01_XL_ORB_BREAK | ALLOWED | SF_OPENING_RANGE_BREAKOUT | Primary entry in OPENING |
| 02_XL_ORB_RETEST | ALLOWED (OPTIONAL) | SF_OPENING_RANGE_BREAKOUT | Higher quality entries |
| 03_XL_FLAG_BREAK | OPTIONAL | SF_BULL_FLAG/SF_TIGHT_FLAG | Enable only when flag detectors certified |
| 04_XL_FLAG_RECLAIM | OPTIONAL | SF_BULL_FLAG/SF_TIGHT_FLAG | As above |
| 05_XL_VWAP_RECLAIM | ALLOWED | SF_KEY_LEVEL_RECLAIM / SF_VWAP_RECLAIM | When reclaiming VWAP |
| 06_XL_EMA_RECLAIM | ALLOWED (OPTIONAL) | SF_KEY_LEVEL_RECLAIM | For pullback continuation |
| 07_XL_HOD_BREAK | ALLOWED | SF_HIGH_OF_DAY_BREAK | Primary entry |
| 08_XL_RANGE_BREAK | ALLOWED | SF_RANGE_EXPANSION | Primary entry |
| 09_XL_ABCD | OPTIONAL | SF_ABCD_CONTINUATION | Only if modeled |
| 10_XL_MEASURED_MOVE | OPTIONAL | SF_RANGE_EXPANSION / measured move | Only if modeled |
| 11_XL_LIQUIDITY_SWEEP_RECLAIM | DENIED | — | Specialised; later |

### 3.2 Setup Families (SF_*) — strategy scope
**ALLOWED (must be supported):**
- SF_RANGE_EXPANSION
- SF_OPENING_RANGE_BREAKOUT
- SF_PREMARKET_HIGH_BREAK
- SF_HIGH_OF_DAY_BREAK
- SF_KEY_LEVEL_BREAK
- SF_KEY_LEVEL_RECLAIM
- SF_RELATIVE_STRENGTH_LEADER
- SF_VOLATILITY_EXPANSION
- SF_MOMENTUM_STAIRCASE
- SF_POWER_HOUR_EXPANSION

**OPTIONAL (may be supported if detectors exist):**
- SF_VOLATILITY_CONTRACTION
- SF_VOLATILITY_SQUEEZE
- SF_COMPRESSION_COIL
- SF_BULL_FLAG
- SF_TIGHT_FLAG

**DENIED (explicitly out-of-scope):**
- All mean-reversion/fade setups: SF_VWAP_FADE, SF_MEAN_REVERSION_*
- Event/halt reversals: SF_EVENT_REVERSAL, SF_HALT_RESUME
- Long-horizon setups: SF_LONG_TERM_*, SF_MACRO_*

### 3.3 Conditions (C_*) — required baseline
**REQUIRED C_* for any entry:**
Market/session:
- C_SESSION_PHASE_ALLOWED, C_TIME_OF_DAY_ALLOWED, C_HALT_STATE_ALLOWED, C_SSR_STATE_ALLOWED
Data quality:
- C_DATA_QUALITY_OK, C_REFERENCE_PRICE_VALID, C_HAS_BID_ASK, C_STALE_DATA_REJECT
- C_SPREAD_WITHIN_LIMIT, C_LIQUIDITY_WITHIN_MIN, C_FLOAT_KNOWN_OR_ALLOWED
Structure/volatility:
- C_LEVELS_BUILT_OK, C_SETUP_FAMILY_ACTIVE, C_INVALIDATION_DEFINED
- C_VOLATILITY_STATE_ALLOWED, C_ATR_WITHIN_BOUNDS
Volume:
- C_RELATIVE_VOLUME_OK, C_ABSOLUTE_VOLUME_OK
Risk:
- C_RISK_ENGINE_APPROVED, C_STRATEGY_PERMISSION_OK, C_NO_TRADE_CONTEXT_FALSE
- C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED, C_SYMBOL_COOLDOWN_EXPIRED

### 3.4 Confirmations (K_*) — required vs optional
**REQUIRED:**
- K_DATA_QUALITY_CONFIRM, K_SPREAD_CONFIRM, K_LIQUIDITY_CONFIRM
- K_VOLUME_CONFIRM, K_RELATIVE_VOLUME_CONFIRM
- K_INVALIDATION_PRESENT_CONFIRM, K_RISK_ENGINE_GREEN_CONFIRM

**OPTIONAL (enable per SF/mode):**
- K_BREAK_AND_HOLD_CONFIRM, K_RETEST_CONFIRM, K_LEVEL_HOLD_CONFIRM
- K_NO_PARABOLIC_EXHAUSTION_CONFIRM, K_NO_TOPPING_TAILS_CONFIRM
- K_MARKET_REGIME_CONFIRM, K_INDEX_TREND_CONFIRM, K_SECTOR_STRENGTH_CONFIRM
- K_VOLATILITY_WINDOW_CONFIRM, K_TIME_OF_DAY_CONFIRM
- K_TAPE_STRENGTH_CONFIRM, K_L2_BID_STACK_CONFIRM, K_L2_ASK_THIN_CONFIRM
- K_NEWS_CATALYST_CONFIRM (only if feed is reliable)

### 3.5 Candlestick patterns — utilisation
**SCP_*:** used only as features into K_* confirmations (never direct triggers).
**MCP_*:** used to activate SF_* and support K_* confirmations.

Minimum used set:
- SCP_EXPANSION_CANDLE, SCP_STRONG_BULL_BODY, SCP_BULLISH_MARUBOZU
- SCP_DOJI, SCP_SPINNING_TOP, SCP_HIGH_WAVE
- SCP_PARABOLIC_EXHAUSTION, SCP_VOLUME_CLIMAX_CANDLE, SCP_EXHAUSTION_WICK
- MCP_EXPANSION_SEQUENCE, MCP_RANGE_EXPANSION, MCP_BREAK_AND_HOLD
- MCP_OPENING_RANGE_SEQUENCE, MCP_BREAK_AND_FAIL, MCP_FAILED_BREAKOUT

### 3.6 Levels/Zones/Invalidations — required
Levels:
- LVL_HIGH_OF_DAY, LVL_VWAP, LVL_OPEN_PRICE, LVL_PREMARKET_HIGH, LVL_PREMARKET_LOW
Zones:
- ZONE_OPENING_RANGE, ZONE_SESSION_RANGE, ZONE_PREMARKET_RANGE
Invalidations:
- INV_LEVEL_LOSS, INV_RANGE_FAILURE, INV_STRUCTURE_BREAK, INV_PATTERN_FAILURE

---

## 4) Traceability requirements (M4/E14)
Every emitted TradeIntent must include:
- `setup_family_id` (SF_*)
- `execution_trigger_id` (XL_*)
- list of required C_* evaluated + failures (if no trade)
- list of required K_* evaluated + failures (if no trade)
- a “snapshot key” of metrics used for ranking/decision

---

## 5) Certification gates (E19/E21)
See `CERTIFICATION_CHECKLIST.md`.

