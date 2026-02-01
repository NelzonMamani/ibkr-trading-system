# 07_SUCCESS_CRITERIA.md
TITLE: Success Criteria — When We Are “Ready”
DATE: 2026-01-31

## 1. Scanner/session correctness
PASS when:
- Scanner outputs `session_label`, `reference_price_type`, `reference_timestamp` for every symbol
- Weekend CLOSED run uses last RTH close (Friday close) as reference
- `pct_change` and `rvol` are either correct or explicitly None with data-quality flags (no silent lies)

## 2. PAPER trading readiness
PASS when:
- PAPER runs full lifecycle end-to-end and writes DB artifacts
- Deterministic harness produces stable outputs across runs
- MICRO risk profile clamps size to 1 share and blocks adds

## 3. Strategy readiness (Ross complete)
PASS when:
- All setup families/patterns from the catalogue are implemented
- Each intent is traceable to a setup family + trigger
- Exhaustion / big-red-volume veto state exists and prevents new entries

## 4. Go-live rule
LIVE must remain disabled unless:
- PAPER PASS (all scenarios)
- LIVE_READ_ONLY parity is acceptable (signals match for same data window)
- MICRO profile runs safely before NORMAL

END
