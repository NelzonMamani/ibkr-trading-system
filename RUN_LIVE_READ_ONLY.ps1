# ================================
# RUN_LIVE_READ_ONLY.ps1
# Live data, no execution
# ================================

Write-Host "Starting LIVE_READ_ONLY..." -ForegroundColor Yellow

# ---- Clear conflicting variables ----
Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue
Remove-Item Env:LIVE_MICRO_ACK -ErrorAction SilentlyContinue
Remove-Item Env:LIVE_MICRO_1_SHARE_ONLY -ErrorAction SilentlyContinue
Remove-Item Env:IBKR_MARKET_DATA_TYPE -ErrorAction SilentlyContinue

# ---- Authoritative runtime ----
$env:RUN_MODE="LIVE_READ_ONLY"

# ---- IBKR ----
$env:IBKR_MARKET_DATA_TYPE="LIVE"
$env:IBKR_PORT="7496"

# ---- Launch ----
python -m src.main