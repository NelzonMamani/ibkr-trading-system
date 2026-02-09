# E21 Mode Parity Matrix

| Mode | Status | Evidence | Notes |
| --- | --- | --- | --- |
| SIM | RUN | harness_run.txt | Harness executed in SIM with mock provider. |
| PAPER | NOT_RUN |  | Broker connectivity unavailable. Run locally: python -m src.e21.harness --run-all --out TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_21 |
| READ_ONLY | NOT_RUN |  | PowerShell runtime not available in CI. Run locally: python -m src.e21.harness --run-all --out TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_21 |
| LIVE | NOT_RUN |  | Requires IBKR connectivity. Run locally: python -m src.e21.harness --run-all --out TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_21 |
