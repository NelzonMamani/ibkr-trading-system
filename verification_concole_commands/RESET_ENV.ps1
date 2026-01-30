# ================================
# RESET_ENV.ps1
# ================================

Write-Host "Resetting environment variables..." -ForegroundColor Yellow

$vars = @(
  "RUN_MODE",
  "SESSION_PHASE_OVERRIDE",
  "SCANNER_DATA_SOURCE",
  "IBKR_MARKET_DATA_TYPE",
  "LIVE_MICRO_ACK",
  "EVENT_REPLAY_MODE"
)

foreach ($v in $vars) {
  Remove-Item "Env:$v" -ErrorAction SilentlyContinue
}

Write-Host "Environment reset complete." -ForegroundColor Green
