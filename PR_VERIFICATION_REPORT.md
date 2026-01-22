# PR Verification Report

## Summary
- Objective: verify pct_change fallback behavior, scanner gate ordering, and mode parity updates with required commands.
- Status: mandatory commands executed; LIVE_READ_ONLY/LIVE_MICRO runs degraded due to IBKR connection refusal in this environment.

---

# Phase 1 — Mandatory Verification Commands

1) Command:
```
python -m compileall -q src
```
Output:
```
(no output; success)
```

2) Command:
```
pytest -q
```
Output (condensed):
```
124 passed, 7 skipped, 4 warnings in 10.21s
```
Warnings (condensed):
```
RuntimeWarning: coroutine 'IB.connectAsync' was never awaited
```

3) Command:
```
python -m src.main --mode SIM --cycles 1
```
Output (condensed):
```
[CONFIG] Resolved runtime configuration (authoritative):
  - RUN_MODE: SIM (resolved)
[SCANNER] MODE=integrated SESSION=REG
[SHUTDOWN] Exiting gracefully. Goodbye!
```

4) Command (with debug flags):
```
DEBUG_MARKET_DATA=true DEBUG_SCANNER=true python -m src.main --mode READONLY --cycles 1
```
Output (condensed):
```
[CONFIG] Resolved runtime configuration (authoritative):
  - RUN_MODE: LIVE_READ_ONLY (resolved)
[IBKR][MD] Connecting host=127.0.0.1 port=7497 client_id=7
API connection failed: ConnectionRefusedError(111, "Connect call failed ('127.0.0.1', 7497)")
[SAFETY] LIVE/LIVE_READ_ONLY/LIVE_MICRO mode violation — entering deterministic safe halt.
[SHUTDOWN] Exiting gracefully. Goodbye!
```

5) Command (with debug flags):
```
DEBUG_MARKET_DATA=true DEBUG_SCANNER=true LIVE_MICRO_ACK=true LIVE_MICRO_1_SHARE_ONLY=true python -m src.main --mode LIVE_MICRO --cycles 1
```
Output (condensed):
```
[CONFIG] Resolved runtime configuration (authoritative):
  - RUN_MODE: LIVE_MICRO (resolved)
[IBKR][MD] Connecting host=127.0.0.1 port=7497 client_id=7
API connection failed: ConnectionRefusedError(111, "Connect call failed ('127.0.0.1', 7497)")
[SCANNER][WARN] Provider connection failed — falling back to MOCK reason=[Errno 111] Connect call failed ('127.0.0.1', 7497)
[SHUTDOWN] Exiting gracefully. Goodbye!
```

---

## Notes
- IBKR connectivity is unavailable in this environment (connection refused on port 7497), so LIVE_READ_ONLY/LIVE_MICRO runs halted or degraded accordingly.
