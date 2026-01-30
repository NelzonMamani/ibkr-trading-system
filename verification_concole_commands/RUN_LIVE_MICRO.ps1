# ================================
# RUN_LIVE_MICRO.ps1
# ================================

Write-Host "Starting LIVE_MICRO trading..." -ForegroundColor Red

Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue

$env:RUN_MODE="LIVE_MICRO"
$env:LIVE_MICRO_ACK="TRUE"
$env:IBKR_PORT="7496"

python -m src.main --strategy ross_momentum
