# ================================
# RUN_SIMULATION.ps1
# Deterministic simulation
# ================================

Write-Host "Starting SIMULATION mode..." -ForegroundColor Green

# ---- Clear conflicting variables ----
Remove-Item Env:RUN_MODE -ErrorAction SilentlyContinue
Remove-Item Env:IBKR_MARKET_DATA_TYPE -ErrorAction SilentlyContinue

# ---- Authoritative runtime ----
$env:RUN_MODE="SIM"

# ---- Launch ----
python -m src.main