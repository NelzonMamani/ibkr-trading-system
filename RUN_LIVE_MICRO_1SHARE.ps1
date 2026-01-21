# ================================
# RUN_LIVE_MICRO_1SHARE.ps1
# Real trading, 1-share max
# ================================

Write-Host "Starting LIVE_MICRO (1-share only)..." -ForegroundColor Red

# ---- Clear conflicting variables ----
Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue
Remove-Item Env:LIVE_MICRO_ACK -ErrorAction SilentlyContinue
Remove-Item Env:LIVE_MICRO_1_SHARE_ONLY -ErrorAction SilentlyContinue
Remove-Item Env:IBKR_MARKET_DATA_TYPE -ErrorAction SilentlyContinue

# ---- Authoritative runtime ----
$env:RUN_MODE="LIVE_MICRO"
$env:LIVE_MICRO_ACK="true"
$env:LIVE_MICRO_1_SHARE_ONLY="true"

# ---- IBKR ----
$env:IBKR_MARKET_DATA_TYPE="LIVE"
$env:IBKR_PORT="7496"   # TWS paper/live as configured

# ---- Launch ----
python -m src.main