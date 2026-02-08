# E15_FAILURE_MODES — RUN MODES AND AUTHORITY

Authoritative system run modes:
- SIM
- PAPER
- READ_ONLY
- LIVE

No other run modes may exist.

LIVE_MICRO, LIVE_1_SHARE, or similar constructs are NOT run modes.
They are risk/portfolio configurations applied INSIDE LIVE.

Invariant:
Execution authority is defined solely by RUN_MODE.
Risk sizing is defined solely by risk/portfolio configuration.

END
