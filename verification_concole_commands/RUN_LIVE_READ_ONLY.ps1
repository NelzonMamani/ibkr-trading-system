# ================================
# RUN_LIVE_READ_ONLY.ps1
# ================================

Write-Host "Starting LIVE_READ_ONLY..." -ForegroundColor Green

Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue
Remove-Item Env:LIVE_MICRO_ACK -ErrorAction SilentlyContinue

$env:RUN_MODE="LIVE_READ_ONLY"
$env:IBKR_PORT="7496"

python -m src.main --strategy ross_momentum --cycles 1
