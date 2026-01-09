#!/usr/bin/env bash
set -euo pipefail

echo "[SMOKE] Running standalone scanner..."
python -m src.scanner.scanner_main

echo "[SMOKE] Running integrated scanner (main.py)..."
python src/main.py

echo "[SMOKE] Watchlist output should be in output/watchlists/"
