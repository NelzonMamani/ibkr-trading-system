# P01_ROSS_MOMENTUM — STRATEGY GOVERNANCE (E19/M7 aligned)
Date: 2026-02-08

## 1) Scope
Ross Momentum is a **LONG-biased** momentum continuation strategy for U.S. small-cap gappers/runners.

## 2) Authority
- Core epochs E0–E21 are treated as implemented/certified.
- Metadata epochs M0–M10 govern canon, contracts, verification, and change control.
- Canon registries (SF_*, XL_*, C_*, K_*, SCP_*, MCP_*, levels/zones) are the only valid identifiers.

## 3) Safety and No-Trade contexts (E16)
Ross MUST emit NO TRADE when any of:
- data quality invalid / stale / missing reference price
- spreads/liquidity violate policy
- risk engine denies (daily loss, consecutive loss cap, position limits)
- halts not allowed (unless allow_halts=True and stability confirm passes)
- parabolic exhaustion / climax top guard triggers (policy-defined)
- topping risk HALT triggers

## 4) Tunable Parameter Authority (locked)
All thresholds that affect behaviour MUST live in `strategy_policy.py`:
- stock selection thresholds (price/gap/%change/rvol/float/volume/spread/catalyst)
- setup specs (micro pullback ratios, flag thresholds, ORB range definition)
- topping risk ratios
- mode/time boundaries
- risk/permitted re-entries caps (if used)

No hidden constants elsewhere.

## 5) Traceability (E1/E14/M4)
Every emitted TradeIntent MUST include:
- SF_* id
- XL_* id
- required C_* snapshot
- required K_* snapshot
- key levels used (e.g., VWAP, HOD, ORB)
- numeric values and thresholds used in decision

## 6) Change control (M8)
Any behavioural change requires:
- explicit change log in governance pack
- parameter diff summary
- re-run certification verification suite (E21)

END
