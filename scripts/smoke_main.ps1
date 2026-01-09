Write-Host "[SMOKE] Running main orchestrator..."
Write-Host "[SMOKE] If IBKR is not running on the configured port, fallback logs are expected."
python -m src.main
