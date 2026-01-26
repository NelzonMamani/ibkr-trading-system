# PR Verification Report

## Summary
- Objective: execute mandatory verification commands for scanner readiness, live-mode safety, and statistical readiness.
- Status: Python checks ran; LIVE_READ_ONLY run failed due to unavailable IBKR connectivity in this environment.

## Log Directory
- `output/verification/`

---

## Mandatory Verification Commands

1) Command:
```
python -m compileall -q src
```
Result: PASS

2) Command:
```
pytest -q
```
Result: PASS
Excerpt:
```
127 passed, 7 skipped in 6.95s
```

3) Command:
```
python -m src.main --mode SIM --cycles 1
```
Result: PASS

4) Command:
```
python -m src.main --mode READONLY --cycles 1
```
Result: FAIL (environment)
Excerpt:
```
ProviderConnectionError: [Errno 111] Connect call failed ('127.0.0.1', 7497)
```

5) Command:
```
python -m src.main --strategy statistical_intraday_momentum --mode SIM --readiness-check
```
Result: PASS
Excerpt:
```
[READINESS] status=PASS
```
