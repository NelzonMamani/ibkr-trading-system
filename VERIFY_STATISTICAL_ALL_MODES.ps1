# VERIFY_STATISTICAL_ALL_MODES.ps1
# Purpose: Mandatory verification commands for Statistical Intraday Momentum readiness.
# Usage (PowerShell):  .\VERIFY_STATISTICAL_ALL_MODES.ps1
# Notes:
# - This script is read-only. It should not place live orders.
# - It requires that src.main supports --readiness-check and --strategy statistical_intraday_momentum.

$ErrorActionPreference = "Stop"

$env:STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED = "true"
$env:SELECTED_STRATEGY = "statistical_intraday_momentum"

Write-Host "=== VERIFY: CLI HELP (modes + strategies) ===" -ForegroundColor Cyan
python -m src.main --help

$modes = @("SIM","READONLY","PAPER","LIVE_READ_ONLY","LIVE_1SHARE","LIVE_MICRO","LIVE")

Write-Host "=== VERIFY: READINESS CHECK ALL MODES ===" -ForegroundColor Cyan
foreach ($mode in $modes) {
    Write-Host ("--- Mode: {0} ---" -f $mode) -ForegroundColor Yellow
    python -m src.main --strategy statistical_intraday_momentum --mode $mode --readiness-check
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("FAIL: readiness-check failed for mode {0} (exit={1})" -f $mode, $LASTEXITCODE) -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "=== VERIFY: NON-FALLBACK (1 cycle) ===" -ForegroundColor Cyan
python -m src.main --strategy statistical_intraday_momentum --mode READONLY --cycles 1
if ($LASTEXITCODE -ne 0) {
    Write-Host ("FAIL: 1-cycle run failed (exit={0})" -f $LASTEXITCODE) -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "PASS: All verification commands succeeded." -ForegroundColor Green
