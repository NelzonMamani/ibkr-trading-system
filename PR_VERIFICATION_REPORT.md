# PR Verification Report

## Summary
- Objective: execute mandatory verification commands for statistical readiness and live-mode scripts.
- Status: Python verification commands passed; PowerShell scripts could not run because `powershell` is not installed in this environment.

## Log Directory
- `output/verification/`

---

## Mandatory Verification Commands

1) Command:
```
python -m compileall -q src
```
Result: PASS
Log: `output/verification/compileall.log`
Excerpt:
```
(no output)
```

2) Command:
```
pytest -q
```
Result: PASS
Log: `output/verification/pytest.log`
Excerpt:
```
124 passed, 7 skipped, 4 warnings in 7.03s
```

3) Command:
```
powershell -ExecutionPolicy Bypass -File .\RUN_LIVE_READ_ONLY.ps1
```
Result: FAIL (environment)
Log: `output/verification/RUN_LIVE_READ_ONLY.log`
Excerpt:
```
bash: command not found: powershell
```

4) Command:
```
powershell -ExecutionPolicy Bypass -File .\RUN_LIVE_MICRO_1SHARE.ps1
```
Result: FAIL (environment)
Log: `output/verification/RUN_LIVE_MICRO_1SHARE.log`
Excerpt:
```
bash: command not found: powershell
```

5) Command:
```
powershell -ExecutionPolicy Bypass -File .\RUN_PAPER_TRADING.ps1
```
Result: FAIL (environment)
Log: `output/verification/RUN_PAPER_TRADING.log`
Excerpt:
```
bash: command not found: powershell
```

6) Command:
```
powershell -ExecutionPolicy Bypass -File .\RUN_SIMULATION.ps1
```
Result: FAIL (environment)
Log: `output/verification/RUN_SIMULATION.log`
Excerpt:
```
bash: command not found: powershell
```

7) Command:
```
powershell -ExecutionPolicy Bypass -File .\VERIFY_STATISTICAL_ALL_MODES.ps1
```
Result: FAIL (environment)
Log: `output/verification/VERIFY_STATISTICAL_ALL_MODES.log`
Excerpt:
```
bash: command not found: powershell
```

---

## Supplemental Checks

8) Command:
```
python -m src.main --strategy statistical_intraday_momentum --mode SIM --readiness-check
```
Result: PASS
Log: `output/verification/readiness_SIM.log`
Excerpt:
```
[READINESS] status=PASS
```
