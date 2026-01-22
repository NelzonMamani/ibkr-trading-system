# RUN_LIVE_MICRO_1SHARE.ps1
Write-Host "Starting LIVE_MICRO (1-share only)..." -ForegroundColor Red

# Authoritative runtime
$env:LIVE_MICRO_ACK="true"
$env:LIVE_MICRO_1_SHARE_ONLY="true"

# If you want LIVE market data:
$env:IBKR_MARKET_DATA_TYPE="LIVE"

# Paper TWS usually 7497; Live TWS usually 7496 (use the one you actually run)
$env:IBKR_PORT="7496"

python -m src.main --mode LIVE_MICRO
