# P01_ROSS_MOMENTUM — STRATEGY CAPABILITY MAP (Complete, No Partials)
Date: 2026-02-08
Authority: E0–E21 + M0–M10; Canon registries (E18/E20)

## 1) Stock Selection (Eligibility)
Primary source references (Ross/Warrior Trading):
- RVOL>=5 baseline; “already up ~10%”; low float ideal <=20M. citeturn0search9turn0search5turn0search17
- Ross uses scanners by price/float/RVOL/% change and real-time HOD momentum scanner concepts. citeturn0search0

### Policy ownership
All thresholds live in `strategies/ross_momentum/strategy_policy.py::StockSelectionSpec`.

**REQUIRED parameters (must exist):**
- price_min, price_max
- gap_min_pct, gap_max_pct (optional)
- pct_change_min (if separate from gap; must be policy-defined)
- rvol_min
- float_max_millions
- require_catalyst
- min_volume, min_premarket_volume
- liquidity_min_dollar_volume, spread_max_pct
- allow_halts, allow_ssr
- watchlist_limit_k, focus_limit_m
- session_allowlist
- ranking_intent / rank_score spec

**REQUIRED provenance fields in CandidateMetrics:**
- reference_price_type (RTH close, premarket last, etc.)
- session_label, asof timestamps
- data_quality flags + gate_checks

---

## 2) Setup Families (SF_*) — classification
Legend: REQUIRED (must be supported), OPTIONAL (supported but off by default), DENIED (explicitly out of scope)

### I. Gap & Open Structure
- SF_GAP_AND_GO — REQUIRED
- SF_OPENING_RANGE_BREAKOUT — REQUIRED
- SF_OPENING_RANGE_FAKEOUT — OPTIONAL
- SF_PREMARKET_HIGH_BREAK — REQUIRED
- SF_PREMARKET_LOW_BREAK — DENIED (LONG-only v1)

### II. Momentum Continuation
- SF_FIRST_PULLBACK — REQUIRED
- SF_SECOND_PULLBACK — OPTIONAL
- SF_MICRO_PULLBACK — REQUIRED
- SF_BULL_FLAG — REQUIRED
- SF_TIGHT_FLAG — REQUIRED
- SF_FLAT_TOP_BREAKOUT — REQUIRED
- SF_ASCENDING_TRIANGLE — OPTIONAL
- SF_MOMENTUM_STAIRCASE — OPTIONAL
- SF_PARABOLIC_CONTINUATION — OPTIONAL (guarded)

### III. Level-Based Structure
- SF_HIGH_OF_DAY_BREAK — REQUIRED
- SF_KEY_LEVEL_RECLAIM — REQUIRED
- SF_KEY_LEVEL_BREAK — OPTIONAL
- SF_PRIOR_DAY_HIGH_BREAK — OPTIONAL
- SF_PRIOR_DAY_CLOSE_RECLAIM — OPTIONAL

### IV. VWAP & Mean Structure
- SF_VWAP_RECLAIM — REQUIRED
- SF_VWAP_TREND_DAY — OPTIONAL (context)
- SF_VWAP_FADE — DENIED (belongs to other strategies)

### VIII. Halt, News & Event
- SF_NEWS_SPIKE — REQUIRED
- SF_HALT_RESUME — OPTIONAL (only if allow_halts=True)
- SF_EARNINGS_REACTION — OPTIONAL
- SF_EVENT_CONTINUATION — OPTIONAL

### IX. Time-of-Day Structure (context overlays)
- SF_OPENING_DRIVE — REQUIRED (mode)
- SF_MIDDAY_COMPRESSION — REQUIRED (mode/context)
- SF_POWER_HOUR_EXPANSION — REQUIRED (mode/context)

All other SF_* → DENIED for Ross v1.

---

## 3) Execution Triggers (XL_*) — classification and mapping
All E18 triggers MUST exist in OS. Ross must classify each.

### XL classification
- 00_XL_MICRO_PULLBACK — REQUIRED
- 01_XL_ORB_BREAK — REQUIRED
- 02_XL_ORB_RETEST — REQUIRED
- 03_XL_FLAG_BREAK — REQUIRED
- 04_XL_FLAG_RECLAIM — OPTIONAL
- 05_XL_VWAP_RECLAIM — REQUIRED
- 06_XL_EMA_RECLAIM — REQUIRED
- 07_XL_HOD_BREAK — REQUIRED
- 08_XL_RANGE_BREAK — OPTIONAL
- 09_XL_ABCD — OPTIONAL
- 10_XL_MEASURED_MOVE — OPTIONAL
- 11_XL_LIQUIDITY_SWEEP_RECLAIM — OPTIONAL

### SF → XL mapping (must be implemented)
- SF_MICRO_PULLBACK → 00_XL_MICRO_PULLBACK
- SF_OPENING_RANGE_BREAKOUT → 01_XL_ORB_BREAK, 02_XL_ORB_RETEST
- SF_BULL_FLAG/SF_TIGHT_FLAG/SF_FLAT_TOP_BREAKOUT → 03_XL_FLAG_BREAK (and optionally 04_XL_FLAG_RECLAIM)
- SF_VWAP_RECLAIM → 05_XL_VWAP_RECLAIM
- SF_FIRST_PULLBACK → 06_XL_EMA_RECLAIM (plus optional 07_XL_HOD_BREAK for add)
- SF_HIGH_OF_DAY_BREAK → 07_XL_HOD_BREAK

---

## 4) Conditions (C_*) — REQUIRED set
Ross requires at minimum:
- C_SESSION_PHASE_ALLOWED
- C_DATA_QUALITY_OK
- C_REFERENCE_PRICE_VALID
- C_STALE_DATA_REJECT
- C_SPREAD_WITHIN_LIMIT
- C_LIQUIDITY_WITHIN_MIN
- C_FLOAT_KNOWN_OR_ALLOWED
- C_RELATIVE_VOLUME_OK
- C_RISK_ENGINE_APPROVED
- C_STRATEGY_PERMISSION_OK
- C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED
- C_SYMBOL_COOLDOWN_EXPIRED
- C_SETUP_FAMILY_ACTIVE
- C_INVALIDATION_DEFINED
- C_NO_TRADE_CONTEXT_FALSE

Optional:
- C_HALT_STATE_ALLOWED, C_SSR_STATE_ALLOWED depending on policy flags

---

## 5) Confirmations (K_*) — REQUIRED vs OPTIONAL
Required (always):
- K_DATA_QUALITY_CONFIRM
- K_SPREAD_CONFIRM
- K_LIQUIDITY_CONFIRM
- K_VOLUME_CONFIRM
- K_RELATIVE_VOLUME_CONFIRM
- K_INVALIDATION_PRESENT_CONFIRM
- K_RISK_ENGINE_GREEN_CONFIRM

Setup-dependent required:
- K_BREAK_AND_HOLD_CONFIRM
- K_RETEST_CONFIRM
- K_LEVEL_HOLD_CONFIRM
- K_PULLBACK_WEAK_VOLUME_CONFIRM
- K_NO_TOPPING_TAILS_CONFIRM
- K_NO_PARABOLIC_EXHAUSTION_CONFIRM

Optional (policy selectable):
- K_TAPE_STRENGTH_CONFIRM
- K_L2_BID_STACK_CONFIRM
- K_L2_ASK_THIN_CONFIRM
- K_NEWS_CATALYST_CONFIRM
- K_TIME_OF_DAY_CONFIRM
- K_MARKET_REGIME_CONFIRM
- K_SECTOR_STRENGTH_CONFIRM
- K_INDEX_TREND_CONFIRM
- K_VOLATILITY_WINDOW_CONFIRM
- K_HALT_RESUME_STABILITY_CONFIRM

---

## 6) Candle pattern utilisation (SCP_*, MCP_*)
Ross must explicitly map candlestick primitives to confirmations/guards.

### SCP_* used (filters/guards)
- Indecision: SCP_DOJI, SCP_SPINNING_TOP, SCP_HIGH_WAVE
- Topping: SCP_GRAVESTONE_DOJI, SCP_LONG_UPPER_WICK, SCP_SHOOTING_STAR
- Momentum: SCP_STRONG_BULL_BODY, SCP_EXPANSION_CANDLE
- Exhaustion: SCP_PARABOLIC_EXHAUSTION, SCP_VOLUME_CLIMAX_CANDLE

### MCP_* used (setup detection)
- MCP_MICRO_PULLBACK_2, MCP_MICRO_PULLBACK_3
- MCP_FIRST_PULLBACK
- MCP_BULL_FLAG, MCP_TIGHT_FLAG, MCP_FLAT_TOP
- MCP_OPENING_RANGE_SEQUENCE
- MCP_BREAK_AND_HOLD, MCP_LEVEL_RECLAIM_SEQUENCE
- MCP_PARABOLIC_EXHAUSTION, MCP_CLIMAX_TOP

---

## 7) Levels/Zones/Invalidations
Required levels for Ross:
- LVL_PREVIOUS_CLOSE, LVL_OPEN_PRICE
- LVL_PREMARKET_HIGH, LVL_PREMARKET_LOW
- LVL_HIGH_OF_DAY, LVL_LOW_OF_DAY
- LVL_PRIOR_DAY_HIGH, LVL_PRIOR_DAY_LOW, LVL_PRIOR_DAY_CLOSE
- LVL_VWAP, LVL_EMA_9, LVL_EMA_20, (optional EMA50/200, SMA50/200)
Zones:
- ZONE_OPENING_RANGE, ZONE_PREMARKET_RANGE, ZONE_SESSION_RANGE
Invalidations (INV_*):
- INV_LEVEL_LOSS, INV_VWAP_LOSS, INV_PATTERN_FAILURE, INV_STRUCTURE_BREAK

END
