# ================================
# RUN_PAPER.ps1
# ================================

Write-Host "Starting PAPER trading..." -ForegroundColor Green

Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue

$env:RUN_MODE="PAPER"
$env:IBKR_PORT="7497"

python -m src.main --strategy ross_momentum
