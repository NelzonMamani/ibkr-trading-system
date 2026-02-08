# 05_VERIFICATION_MATRIX_BY_MODE

## Required run modes
Authoritative run modes:
- SIM
- PAPER
- READ_ONLY
- LIVE

(LIVE_MICRO is not a mode; it is a LIVE risk configuration.)

## Verification matrix (minimum)
The harness must run the following suites:

### SIM (determinism + correctness)
- Synthetic scenario suite (fast, deterministic)
- Recorded scenario replay (known regressions)
- Strategy policy translation output validation
- Full lifecycle: enter → add → trail → exit

### PAPER (broker semantics + async parity)
- Order submit/ack/reject handling
- Partial fills + fill reconciliation
- Cancel/replace lifecycle if supported
- Position reconciliation after restart
- Market data snapshot + timing boundaries

### READ_ONLY (safety)
- Ensure zero broker order submissions
- Ensure intents are logged but marked non-executable
- Ensure audit artifacts are still produced

### LIVE (safety drills only, execution optionally disabled by default)
- Connectivity + market data health checks
- Kill-switch drill (no new orders)
- If execution enabled: micro-risk “canary” with strict caps and operator confirmation workflows as defined by system law

## Declared allowed differences by mode
Any difference must be documented in:
- M3 mode semantics epoch
- and referenced here as a dependency
