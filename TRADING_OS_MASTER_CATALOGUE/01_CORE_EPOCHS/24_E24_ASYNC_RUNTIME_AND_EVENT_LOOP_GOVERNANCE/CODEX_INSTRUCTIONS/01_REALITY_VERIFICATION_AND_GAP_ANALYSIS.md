# 01 — Reality Verification and Gap Analysis

## A) Reproduce failure (must be in evidence notes)
Run:
```bash
pytest -q
```
Confirm the failure references:
- `eventkit.util.get_event_loop()` and/or
- `ib_insync` import chain
- Python 3.14 asyncio error: no current event loop

## B) Identify import chains that trigger it
At minimum:
- `src/scanner/providers/ibkr_provider.py` (imports `ScannerSubscription`)
- `src/ibkr/market_data_client.py` (imports `IB`, `Stock`)
- any other module importing `ib_insync` at import time

## C) Determine current runtime bootstrap entrypoints
List the repo’s entrypoints that should own loop creation, e.g.:
- orchestrator runner
- harness runner
- any CLI entry

## Deliverable of this step
A short written gap note (in PR description or evidence report) describing:
- where the loop error originates
- why it occurs under Python 3.14
- what minimal fix strategy you will apply

