# P04 — Long Horizon Value — STRATEGY GOVERNANCE
**Catalogue path:** `03_STRATEGIES/P04_LONG_HORIZON_VALUE/GOVERNANCE/STRATEGY_GOVERNANCE.md`  
**Timestamp:** 2026-02-08T01:09:09Z

## 1) Boundary
- Long-horizon only; no intraday setups, no day-trading cadence.
- Entries are tranche-based and allocation-aware (E10/E17).
- All tunables must live in policy.

## 2) Invariants
- NO PARTIALS across canon registries
- Traceability for all decisions (E14/M4)
- Mode parity across SIM/PAPER/READ_ONLY/LIVE-safety
- Data provenance for all fundamental/valuation features (M10)

## 3) No-trade contexts (E16)
- Data quality failures
- Liquidity/spread failures
- Risk engine veto / allocation limit reached
- Market closed for live orders (schedule next open)
- Corporate action / symbol not orderable / halted

## 4) Change control (M8)
All changes are policy parameter changes + verification + certification note.

