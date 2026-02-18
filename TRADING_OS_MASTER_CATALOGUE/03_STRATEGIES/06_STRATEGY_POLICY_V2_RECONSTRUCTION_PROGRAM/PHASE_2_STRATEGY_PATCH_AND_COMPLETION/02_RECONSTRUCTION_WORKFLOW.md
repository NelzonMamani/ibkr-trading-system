# 02 — Reconstruction Workflow

## Batch Strategy
Reconstruct in waves to avoid chaos, but the end-state is all strategies CERTIFIED.

Recommended waves (keep total = 19 strategies):
- Wave 1: P02–P04 (core exemplars)
- Wave 2: P05–P08
- Wave 3: P09–P12
- Wave 4: P13–P16
- Wave 5: P17–P20

## Per-Strategy Steps (Must Follow)
1) Confirm whether it is default-only.
2) Fill D0: identity + mode semantics notes (SIM/PAPER/READ_ONLY/LIVE non-empty) + CLOSED semantics.
3) D1: selection_plan + stock_selection_law + liquidity_sanity_model (explicit halt policy) + ranking rationale (or NOT_APPLICABLE token RANK).
4) D2: setup_families + pattern_catalog + structure_model levels.
5) D3/D4: confirmations list includes data-quality + liquidity/spread + volume/rvol + level behaviour.
6) D5: trigger entries (>=1) mapped to setup families.
7) D6: intrabar doctrine with phase_specs+timeframe_map OR explicit NOT_APPLICABLE token INTRABAR.
8) D7: risk_model + safety rules + session_reference_law (pct_change_reference/gap_reference non-empty).
9) D8: exit rules + trailing rules (+ bailout doctrine).
10) D9: position management notes + scaling/partials explicitly.
11) D10: required_fields include symbol,last_price and pct_change|volume|rvol; notes include pause/reject behaviour.
12) D11: explicit safety escalation path (must not be default-only).
13) D12: execution constraints preferred_order_types + notes.
14) D13: timeframe authority explicit (cadence rules or intrabar N/A).
15) D14: scaling doctrine explicit notes + max_adds_per_position >= 0.

## After Each Wave
- `python -m compileall src`
- `pytest -q`
- Confirm Matrix V2 shows CERTIFIED for the upgraded strategies.
