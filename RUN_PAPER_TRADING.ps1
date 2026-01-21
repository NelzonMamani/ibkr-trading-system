# ================================
# RUN_PAPER_TRADING.ps1
# IBKR paper trading
# ================================

Write-Host "Starting PAPER TRADING mode..." -ForegroundColor Cyan

# ---- Clear conflicting variables ----
Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue
Remove-Item Env:LIVE_MICRO_ACK -ErrorAction SilentlyContinue
Remove-Item Env:LIVE_MICRO_1_SHARE_ONLY -ErrorAction SilentlyContinue
Remove-Item Env:IBKR_MARKET_DATA_TYPE -ErrorAction SilentlyContinue

# ---- Authoritative runtime ----
$env:RUN_MODE="PAPER"

# ---- IBKR ----
$env:IBKR_MARKET_DATA_TYPE="LIVE"
$env:IBKR_PORT="7497"   # Paper TWS

# ---- Launch ----
python -m src.main