# 08_FAILURE_INJECTION_TASKS

Codex must implement failure drills:

- Market data disconnect mid-trade
- Broker disconnect with open positions
- Partial fill then crash
- Forced process restart
- Order rejection scenarios

Each drill must:
- Be reproducible
- Produce recovery artifacts
- PASS or FAIL clearly

Silent recovery is forbidden.
