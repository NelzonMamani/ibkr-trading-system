#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_21"

echo "[E21] Running harness -> ${OUTPUT_DIR}"
python -m src.e21.harness --run-all --out "${OUTPUT_DIR}"
