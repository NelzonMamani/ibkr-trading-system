# ================================
# RUN_SIM.ps1
# ================================

Write-Host "Starting SIM mode..." -ForegroundColor Green

Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue
Remove-Item Env:IBKR_MARKET_DATA_TYPE -ErrorAction SilentlyContinue

$env:RUN_MODE="SIM"
$env:SCANNER_DATA_SOURCE="MOCK"

python -m src.main --strategy ross_momentum --cycles 2
