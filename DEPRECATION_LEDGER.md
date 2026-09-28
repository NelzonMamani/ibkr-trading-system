# DEPRECATION_LEDGER.md

## Compatibility / Superseded Entries
- READONLY CLI alias -> compatibility-only; canonical mode is READ_ONLY.
- Governing truth: src/config/runtime_config.py RunMode enum.
- Evidence: output/audit/e23/* READ_ONLY and PAPER boot logs.


## W01 Scanner / News / Market Data

- Deleted `src/scanner/news_engine.py`, `scanner.py`, and `scanner_live_readonly.py` after caller migration. Their independent RSS, teaching/live selection and READ_ONLY mock-fallback bodies are retired.
- Dated master scanner command delegates to `scanner_main.main`; `_selftest` now imports the canonical command. Remove the dated alias after external command users migrate for a release.
- `src/data/news/news_provider.py` only re-exports the canonical prep result adapter; no independent retrieval or cache remains.
- Old scanner reference/session/identity/market-metrics paths, core manager snapshot path and data float provider/worker paths only re-export their `src/market_data` implementations. All repository operational consumers use canonical imports. Remove aliases after external imports migrate for a release.
- Retained legacy news-cache serialization is read through the canonical evidence store with issuer and time revalidation. Remove the legacy shape only after a separate persisted-data migration decision.
- Unused prep-news conversion helpers in scanner runner were deleted; active strategy projections and derived change-signature memo remain.

Authority, caller map, preserved behavior, defects and evidence: `docs/architecture/W01_OWNERSHIP.md`.
