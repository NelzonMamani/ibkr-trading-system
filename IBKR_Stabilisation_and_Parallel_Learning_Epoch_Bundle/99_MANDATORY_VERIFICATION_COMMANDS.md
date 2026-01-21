# 99 — MANDATORY VERIFICATION COMMANDS (OFFICIAL QUALITY GATE)

These commands are mandatory after each instruction document (01, 02, 03) and after the Learning Epoch completion.

## 0) Environment sanity (PowerShell)
- `python --version`
- `pip --version`
- Confirm you are in `.venv`

## 1) Compile
```powershell
python -m compileall -q src
```

## 2) Unit tests
```powershell
pytest -q
```

## 3) Config dump (smoke)
```powershell
python -m src.config.config_dump
```

## 4) One-cycle runtime smoke (safe, deterministic)
### A) Teaching / no orders
```powershell
$env:EXECUTION_ENABLED="false"
python -m src.main --mode LIVE_MICRO --cycles 1
```

### B) LIVE_MICRO guardrails (orders allowed, but 1-share safety enforced)
```powershell
$env:LIVE_MICRO_ACK="true"
$env:LIVE_MICRO_1_SHARE_ONLY="true"
$env:LIVE_MICRO_MAX_POSITIONS="5"
$env:LIVE_MICRO_MAX_DAILY_LOSS="10"
$env:EXECUTION_ENABLED="true"
$env:IBKR_READONLY_ENABLED="false"
$env:IBKR_ORDER_TRANSLATION_ENABLED="true"
$env:IBKR_ORDER_SUBMISSION_ENABLED="true"
$env:SCANNER_SYMBOLS="AAPL,TSLA,NVDA,AMD,SPY"
python -m src.main --mode LIVE_MICRO --cycles 1
```

## Required verification report output (must be provided by Codex)
- Status: PASS/FAIL
- Command-by-command results:
  - compileall: PASS/FAIL
  - pytest: PASS/FAIL (include summary line)
  - config_dump: PASS/FAIL (include key resolved fields)
  - run cycle A: PASS/FAIL
  - run cycle B: PASS/FAIL
- If any FAIL:
  - fix
  - re-run full suite
  - do not proceed until PASS

END
