# P09_RANGE_BOUND_FADE — ALGORITHM (Exhaustive, Certification-Grade)
**Timestamp:** 2026-02-08T01:28:21Z  
**Strategy ID:** P09_RANGE_BOUND_FADE  
**Intent:** Intraday range/rotation fade with strict invalidations; not trend chasing.  
**Law:** NO PARTIALS. Canon registries must be fully classified and mapped for this strategy.

## 1) Decision pipeline (must be implemented)
1. Build Universe & Stock Selection (policy-owned tunables)
2. Produce Watchlist K → Focus M (deterministic caps)
3. For each Focus symbol: evaluate REQUIRED C_* conditions
4. Activate one or more SF_* setups (allowed only)
5. Run REQUIRED K_* confirmations (+ optional per setup/mode)
6. Fire exactly one XL_* trigger for the chosen setup
7. Emit TradeIntent with SF/XL/C/K/INV trace fields
8. OS engines execute: E2 lifecycle + E3 risk + E5 execution authority
9. Record decision artifact every cycle (E14/M4) regardless of trade/no-trade

## 2) Canon registries (complete classification)
### Setup Families
**ALLOWED:** SF_BOX_RANGE, SF_RANGE_FAILURE, SF_RANGE_BOUND_FADE, SF_VWAP_FADE, SF_KEY_LEVEL_RECLAIM  
**DENIED:** SF_GAP_AND_GO, SF_OPENING_RANGE_BREAKOUT, SF_MICRO_PULLBACK, SF_BULL_FLAG  

### Execution Triggers (XL_*)
**Canonical list:** 00_XL_MICRO_PULLBACK, 01_XL_ORB_BREAK, 02_XL_ORB_RETEST, 03_XL_FLAG_BREAK, 04_XL_FLAG_RECLAIM, 05_XL_VWAP_RECLAIM, 06_XL_EMA_RECLAIM, 07_XL_HOD_BREAK, 08_XL_RANGE_BREAK, 09_XL_ABCD, 10_XL_MEASURED_MOVE, 11_XL_LIQUIDITY_SWEEP_RECLAIM  
**ALLOWED:** 05_XL_VWAP_RECLAIM, 06_XL_EMA_RECLAIM, 11_XL_LIQUIDITY_SWEEP_RECLAIM  
**DENIED (all others):** any XL_* not listed as allowed.

### Conditions (C_*) — REQUIRED baseline
REQUIRED: C_DATA_QUALITY_OK, C_REFERENCE_PRICE_VALID, C_STALE_DATA_REJECT, C_HAS_BID_ASK, C_SPREAD_WITHIN_LIMIT, C_LIQUIDITY_WITHIN_MIN, C_RISK_ENGINE_APPROVED, C_STRATEGY_PERMISSION_OK, C_NO_TRADE_CONTEXT_FALSE, C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED, C_SYMBOL_COOLDOWN_EXPIRED, C_LEVELS_BUILT_OK, C_INVALIDATION_DEFINED, C_SETUP_FAMILY_ACTIVE, C_SESSION_PHASE_ALLOWED, C_TIME_OF_DAY_ALLOWED, C_HALT_STATE_ALLOWED, C_SSR_STATE_ALLOWED  
Strategy may add stricter, setup-specific conditions, but cannot remove any required ones.

### Confirmations (K_*) — REQUIRED baseline
REQUIRED: K_DATA_QUALITY_CONFIRM, K_SPREAD_CONFIRM, K_LIQUIDITY_CONFIRM, K_INVALIDATION_PRESENT_CONFIRM, K_RISK_ENGINE_GREEN_CONFIRM  
Plus per-setup OPTIONAL confirmations (must be declared in policy mapping).

## 3) Entry templates (SF + XL)
Codex must implement explicit templates mapping each allowed SF_* to an allowed XL_* trigger and required K_* confirmations.
No template → no trade.

## 4) Invalidations (INV_*)
Every entry must define invalidation:
- INV_LEVEL_LOSS / INV_RANGE_FAILURE / INV_PATTERN_FAILURE / INV_STRUCTURE_BREAK / INV_VWAP_LOSS as applicable.
Codex must map each SF_* to its invalidation set.

## 5) Mode parity (SIM/PAPER/READ_ONLY/LIVE)
- SIM: full cycle logic, no broker dependency
- PAPER: intents → paper execution provider → DB writes
- READ_ONLY: intents and logs only, no orders
- LIVE: execution authority + risk veto enforced; safe defaults.

END
