Write-Host "[SMOKE] Running standalone scanner..."
python -m src.scanner.scanner_main

Write-Host "[SMOKE] Running integrated scanner (main.py)..."
python src/main.py

Write-Host "[SMOKE] Watchlist output should be in output/watchlists/"
