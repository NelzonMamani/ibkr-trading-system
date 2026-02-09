$ErrorActionPreference = "Stop"

$OutputDir = "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_21"

Write-Host "[E21] Running harness -> $OutputDir"
python -m src.e21.harness --run-all --out $OutputDir
