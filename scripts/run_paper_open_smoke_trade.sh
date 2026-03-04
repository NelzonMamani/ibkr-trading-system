#!/usr/bin/env bash
set -euo pipefail

python -m compileall src
python verification_scripts/paper_open_smoke_trade.py
