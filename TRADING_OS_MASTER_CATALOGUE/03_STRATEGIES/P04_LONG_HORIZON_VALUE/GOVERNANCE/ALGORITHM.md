# P04 — Long Horizon Value — ALGORITHM (Canonical, Complete Coverage)
**Catalogue path:** `03_STRATEGIES/P04_LONG_HORIZON_VALUE/GOVERNANCE/ALGORITHM.md`  
**Timestamp:** 2026-02-08T01:09:09Z  
**Authority:** Trading OS Core E0–E21 + Metadata M0–M10 (LOCKED).  
**Rule of law:** **NO PARTIALS.** Every canonical registry item is classified for this strategy.

---

## 0) Strategy intent
P04_LONG_HORIZON_VALUE is a **long-horizon** strategy focused on purchasing assets at a discount to intrinsic value and holding through multi-month to multi-year cycles, using staged entries, valuation bands, and disciplined risk controls.

This strategy is **not** intraday. It must not leak intraday momentum or mean-reversion microstructure behaviours into its decisioning.

---

## 1) Inputs / Outputs

### Inputs (from OS)
- Market state (open/closed) + data quality + reference prices (E4)
- Long-horizon price history (daily/weekly/monthly bars) + derived levels
- Fundamental/valuation features (if provided by the OS; otherwise treated as external enrichment) with provenance (M10)
- Regime context (macro regime flags if present; E8)
- Allocation/risk engine constraints (E3/E10/E16/E17)
- Decision artifact & audit logging (E14/M4/M7)

### Outputs
- `TradeIntent` objects for:
  - ENTRY (initial tranche)
  - ADD (subsequent tranches)
  - TRIM / EXIT
- Required trace fields:
  - `setup_family_id (SF_*)`
  - `execution_trigger_id (XL_*)` (long-horizon usage)
  - evaluated `C_*` + failures
  - evaluated `K_*` + failures
  - invalidation (`INV_*`) defined
  - rationale including valuation/quality signals + band/target

---

## 2) Modes and timeframes (M3)
Run modes (SIM/PAPER/READ_ONLY/LIVE) must be supported with parity (E7).
Timeframes:
- Primary structure: WEEKLY + DAILY
- Execution: DAILY (end-of-day) or scheduled periodic checks
- Optional: MONTHLY for macro zones and rebalancing cadence

---

## 3) Stock selection (long-horizon universe)
Universe is typically broad (e.g., large/mid caps, quality screens). The OS must enforce:
- Data provenance (M10)
- Sector/region constraints if configured
- Minimum liquidity (even for long-horizon, to ensure tradability)

Ranking is based on:
- Valuation discount (intrinsic vs market)
- Quality signals (profitability, leverage, cash flow stability) if available
- Regime compatibility (macro)
- Technical value zones (weekly bases, long-term accumulation)

Outputs: Watchlist K and Focus M for deployment capital.

---

## 4) Canonical Conditions (C_*) — REQUIRED baseline
This strategy must respect the same OS safety gates:

Market/Session:
- C_TIME_OF_DAY_ALLOWED (for scheduled execution windows)
- C_SESSION_PHASE_ALLOWED (often "REG" only unless configured)
- C_MARKET_IS_OPEN (for live order submission; may schedule next open)
Data quality:
- C_DATA_QUALITY_OK
- C_REFERENCE_PRICE_VALID
- C_STALE_DATA_REJECT
- C_HAS_BID_ASK (for orderable markets)
- C_SPREAD_WITHIN_LIMIT (wider tolerance than intraday, policy-defined)
- C_LIQUIDITY_WITHIN_MIN
Risk/Permission:
- C_RISK_ENGINE_APPROVED
- C_STRATEGY_PERMISSION_OK
- C_NO_TRADE_CONTEXT_FALSE
- C_SYMBOL_COOLDOWN_EXPIRED

Note: C_RELATIVE_VOLUME_OK is typically DENIED/IGNORED here unless used for liquidity sanity checks.

---

## 5) Canonical Confirmations (K_*) — REQUIRED vs OPTIONAL

### REQUIRED (always)
- K_DATA_QUALITY_CONFIRM
- K_SPREAD_CONFIRM
- K_LIQUIDITY_CONFIRM
- K_INVALIDATION_PRESENT_CONFIRM
- K_RISK_ENGINE_GREEN_CONFIRM

### OPTIONAL (long-horizon)
- K_MARKET_REGIME_CONFIRM (macro)
- K_SECTOR_STRENGTH_CONFIRM
- K_INDEX_TREND_CONFIRM
- K_TIME_OF_DAY_CONFIRM (scheduled windows)
- K_NEWS_CATALYST_CONFIRM (only for risk adjustments, not entry chasing)

Technical confirmations (weekly/daily):
- K_LEVEL_HOLD_CONFIRM
- K_RETEST_CONFIRM
- K_BREAK_AND_HOLD_CONFIRM (for breakout from base when applicable)

---

## 6) Setup Families (SF_*) — complete classification

### ALLOWED (core long-horizon)
- SF_DAILY_TREND_PULLBACK
- SF_WEEKLY_BASE_BREAKOUT
- SF_LONG_TERM_ACCUMULATION
- SF_LONG_TERM_DISTRIBUTION (as exit/risk flag)
- SF_MACRO_REGIME_SHIFT (as allocation/risk modifier)

### OPTIONAL (conditional)
- SF_KEY_LEVEL_RECLAIM (weekly support reclaim)
- SF_BOX_RANGE (weekly base)
- SF_COMPRESSION_COIL (weekly compression)

### DENIED (explicitly out-of-scope)
Intraday/time-of-day setups:
- SF_OPENING_DRIVE, SF_POWER_HOUR_EXPANSION, SF_OPENING_RANGE_* 
Intraday momentum/fade:
- SF_MICRO_PULLBACK, SF_FIRST_PULLBACK, SF_BULL_FLAG, SF_VWAP_RECLAIM (intraday), SF_VWAP_FADE
Event/halt:
- SF_HALT_RESUME, SF_NEWS_SPIKE (as entry), SF_EVENT_CONTINUATION (as entry)

---

## 7) Execution Triggers (XL_*) — long-horizon usage (complete list)

Long-horizon uses XL_* as **mechanical event primitives** on DAILY/WEEKLY bars.

### ALLOWED
- 06_XL_EMA_RECLAIM (weekly/daily trend reclaim)
- 08_XL_RANGE_BREAK (weekly base breakout)
- 10_XL_MEASURED_MOVE (target projection / trim planning)
- 09_XL_ABCD (optional; only if modeled on weekly/daily)

### OPTIONAL
- 05_XL_VWAP_RECLAIM (only if a long-horizon anchored VWAP is implemented and certified)
- 12_XL_LIQUIDITY_SWEEP_RECLAIM (usually denied; optional only for capitulation patterns if modeled)

### DENIED (as long-horizon entry triggers)
- 00_XL_MICRO_PULLBACK
- 01_XL_ORB_BREAK / 02_XL_ORB_RETEST
- 03/04 flag triggers
- 07_XL_HOD_BREAK (intraday)

---

## 8) Candlestick patterns (SCP_*, MCP_*) — utilisation

SCP/MCP are used as features for:
- accumulation/distribution evidence
- capitulation/exhaustion filters
- base formation quality

### SCP_* (weekly/daily)
- SCP_DOJI, SCP_SPINNING_TOP (indecision)
- SCP_VOLUME_CLIMAX_CANDLE, SCP_EXHAUSTION_WICK, SCP_PARABOLIC_EXHAUSTION (capitulation flags)
- SCP_STRONG_BULL_BODY / BEAR_BODY (trend health)
- Atomic primitives mandatory

### MCP_* (weekly/daily sequences)
- MCP_ACCUMULATION_SEQUENCE
- MCP_DISTRIBUTION_SEQUENCE
- MCP_RANGE_ROTATION
- MCP_BREAK_AND_HOLD
- MCP_BREAK_AND_FAIL (risk flag)
- MCP_MEASURED_MOVE_SEQUENCE (target planning)

---

## 9) Levels/Zones/Invalidations
Long-horizon levels:
- LVL_SMA_200, LVL_EMA_200, LVL_SMA_50, LVL_EMA_50
- LVL_WEEKLY_HIGH/LOW, LVL_MONTHLY_HIGH/LOW
Zones:
- ZONE_LONG_TERM_BASE, ZONE_ACCUMULATION, ZONE_DISTRIBUTION
Invalidations:
- INV_LEVEL_LOSS (weekly support loss)
- INV_STRUCTURE_BREAK (base break failure)
- INV_PATTERN_FAILURE

---

## 10) Portfolio & allocation interaction (E10/E17)
Entries are tranche-based:
- Tranche 1: initial starter at discount band
- Tranche 2/3: add on confirmation (retest, reclaim)
Exits/trims:
- trim into strength per measured move targets or valuation band normalization
Risk constraints:
- max position size per name
- max sector exposure
- drawdown limits

---

## 11) Completeness standard
Complete when:
- Canon registries are fully classified and mapped
- Policy exposes all tunables (valuation bands, tranche sizing, cadence, risk bounds)
- E21 simulation demonstrates multi-cycle persistence and correct behaviour in SIM/PAPER/READ_ONLY/LIVE-safety.

