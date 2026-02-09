# E21 Failure Drills Report

| Drill | Expected | Observed | Result |
| --- | --- | --- | --- |
| FAIL_STALE_REFERENCE_PRICE | Block trades when reference price age exceeds threshold. | Blocked | PASS |
| FAIL_DATA_QUALITY_MISSING_BID_ASK | Block trades when bid/ask data is missing. | Blocked | PASS |
| FAIL_SPREAD_TOO_WIDE | Block trades when spread exceeds 5%. | Blocked (spread=8.00%) | PASS |
| FAIL_LIQUIDITY_TOO_LOW | Block trades when liquidity falls below 10% of average. | Blocked | PASS |
| FAIL_CONTRACT_INVALID_FOUNDATION_COMPONENT | Reject unknown foundation component IDs. | Blocked (SF_UNKNOWN) | PASS |
