# PHASE 24 Scanner Implementation Report

## Scanner call graph (before → after)

### Integrated mode (main.py)
- **Before:** `src/main.py` → `CoreOrchestrator.run_forever()` → `CoreOrchestrator._run_once_inner()` → `Scanner.run_scan_cycle()` / `LiveReadOnlyScanner.run_scan_cycle()` (teaching or live-readonly candidates).
- **After:** `src/main.py` → `CoreOrchestrator.run_forever()` → `CoreOrchestrator._run_once_inner()` →
  - `Scanner.run_scan_cycle()` / `LiveReadOnlyScanner.run_scan_cycle()` (existing candidate flow, now tolerant of IBKR failure via mock fallback)
  - `run_scanner_cycle(mode="integrated")` (Phase 24 canonical scan + filtered watchlist print + return payload)

### Standalone mode (scanner_main.py)
- **Before:** `python -m src.scanner.scanner_master_v2026_01_06_07` (legacy entry point with master printer).
- **After:** `python -m src.scanner.scanner_main` → `run_scanner_cycle(mode="standalone")` → canonical master printer + watchlist output + watchlist persistence.

## 54-field computation
- Canonical field definitions: `src/scanner/contracts.py` (`CANONICAL_FIELD_ORDER`, `ScannerRow54`).
- Data sources:
  - Price + volume: `src/scanner/providers` (IBKR or MOCK providers).
  - Float: provider data (MOCK uses optional cache).
  - News: `src/news/verified_sources.py`, `src/news/news_fetcher.py`, `src/news/news_normalizer.py`.
  - Fire indicator + news heat: `src/news/news_heat.py` (news-only derivation).
- Field mapping into canonical row: `src/scanner/field_mapper.py` (`build_scanner_row54`).

## AUTO_FALLBACK data flow
- Provider selection: `src/scanner/providers/factory.py` (`build_provider`).
- IBKR → MOCK fallback on connect failure, with `[SCAN][FALLBACK]` log marker.

## Filters, watchlist, and return object
- Filters: `src/scanner/filters.py` (`passes_ross_5_pillars`, `passes_catalyst_eligibility`).
- Filtered watchlist assembly + ranking: `src/scanner/scanner_runner.py` (`_apply_filters`, `_rank_watchlist`).
- Watchlist return payload (symbols + rows + timestamps + version): `src/scanner/scanner_runner.py` (`run_scanner_cycle`).
