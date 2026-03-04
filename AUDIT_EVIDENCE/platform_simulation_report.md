# Platform Simulation Report

Generated at: `2026-03-04T11:37:20.518871+00:00`

Simulated chain: `scanner -> watchlist -> strategy runner -> intents -> execution admission -> simulated broker fills -> portfolio state`

- scanner candidates: 2
- watchlist size: 2
- strategy intents: 4
- admitted intents: 3
- blocked intents: 1
- simulated fills attempted: 3

| Fill symbol | status | fill_status | filled_qty |
|---|---|---|---:|
| AAPL | REJECTED | NONE | 0 |
| AAPL | NOT_FILLED | NONE | 0 |
| AAPL | EXPIRED | NONE | 0 |

Blocked intents:
- AAPL: INTENT_NOT_EXECUTABLE, MANUAL_APPROVAL_MISSING
