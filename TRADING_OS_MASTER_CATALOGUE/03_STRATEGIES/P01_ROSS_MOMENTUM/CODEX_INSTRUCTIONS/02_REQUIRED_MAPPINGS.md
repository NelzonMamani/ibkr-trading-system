# FILE: 02_REQUIRED_MAPPINGS.md
# TITLE: Required Ross Mappings (No Partials)
Date: 2026-02-08

## A) Setup Families (SF_*)
Implement explicit classification lists in `strategy_policy.py`:
- ALLOWED_SF: all SF_* marked REQUIRED/OPTIONAL in GOVERNANCE/STRATEGY_CAPABILITY_MAP.md
- DENIED_SF: all others (explicit)

## B) Execution Triggers (XL_*)
Implement:
- ALLOWED_XL (required + optional)
- SF_TO_XL mapping (dict) exactly as specified

## C) Conditions (C_*)
Implement:
- REQUIRED_C list (and optional list toggles)
Runner must enforce REQUIRED_C prior to any trigger evaluation.

## D) Confirmations (K_*)
Implement:
- REQUIRED_K_COMMON
- REQUIRED_K_BY_SF (mapping)
- OPTIONAL_K (feature toggles)
Runner must compute/store confirmation results in trace payload.

## E) Candlestick Patterns
Implement:
- USED_SCP and USED_MCP lists
- Map SCP/MCP outputs into confirmations:
  - K_NO_TOPPING_TAILS_CONFIRM uses SCP_LONG_UPPER_WICK / SCP_GRAVESTONE_DOJI / SCP_SHOOTING_STAR etc.
  - K_PULLBACK_WEAK_VOLUME_CONFIRM may use MCP_MICRO_PULLBACK_2/3 etc.

## F) Levels/Zones/Invalidations
Ensure StrategyContext provides required LVL_* and ZONE_*.
Implement invalidation references per SF/XL:
- INV_VWAP_LOSS, INV_LEVEL_LOSS, INV_PATTERN_FAILURE etc.

END
