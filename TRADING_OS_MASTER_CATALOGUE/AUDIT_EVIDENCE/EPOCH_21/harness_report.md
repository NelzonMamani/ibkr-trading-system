# E21 Harness Summary

Verdict: **PASS**

## Scenarios
- SCN_BULL_FLAG_COMPRESSION: Bull flag with compressing ranges.
- SCN_GAP_AND_GO_BASIC: Gap up with bullish continuation and opening range break.
- SCN_HEAD_AND_SHOULDERS_BASIC: Head and shoulders baseline swing structure.
- SCN_LIQUIDITY_SWEEP_RECLAIM: Sweep and reclaim near demand zone.
- SCN_MODE_PARITY_SIM_PAPER_READONLY: Mode parity placeholder across SIM/PAPER/READ_ONLY/LIVE.
- SCN_NO_TRADE_CONTEXT_VETO: No-trade context veto at portfolio normalisation.
- SCN_PORTFOLIO_NON_INTERFERENCE: Portfolio arbitration does not mutate strategy signals.
- SCN_RANGE_BREAK_AND_FAIL: Range break and failure back into the band.
- SCN_VWAP_RECLAIM_BASIC: Price reclaims VWAP with steady bid.

## Failure Drills
- FAIL_STALE_REFERENCE_PRICE: PASS (Blocked)
- FAIL_DATA_QUALITY_MISSING_BID_ASK: PASS (Blocked)
- FAIL_SPREAD_TOO_WIDE: PASS (Blocked (spread=8.00%))
- FAIL_LIQUIDITY_TOO_LOW: PASS (Blocked)
- FAIL_CONTRACT_INVALID_FOUNDATION_COMPONENT: PASS (Blocked (SF_UNKNOWN))
