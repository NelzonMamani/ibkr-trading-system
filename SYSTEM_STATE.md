# SYSTEM STATE
## Current Authoritative Runtime State

CURRENT_PHASE: 24
SYSTEM_MODE: LIVE_READ_ONLY with MOCK fallback
EXECUTION_STATUS: HARD DISABLED
BROKER_WRITE_ACCESS: DISABLED

### Scanner Contract
- Canonical output contract: 54 fields
- Unfiltered universe: 50 symbols (TOP_GAINERS_COUNT)
- Watchlist output: top 15 after Ross-aligned filters
- Scanner must always emit:
  - candidates_count
  - enriched_count
  - excluded_count
  - watchlist_count
  - Top exclusion reasons when watchlist_count == 0

### News Status
- News is best-effort and non-blocking.
- RSS failures are expected and summarized, not spammed.
- If all feeds fail or verified_rss.txt is empty, news is degraded and watchlist still produces output.

### IBKR Read-Only Status
- Execution is HARD DISABLED.
- Scanner must never request openOrders or completedOrders.
- Market data uses qualified contracts and snapshot lifecycle management.
- Per-symbol IBKR errors are downgraded with exclusion reasons.
- If IBKR fails entirely, switch to MOCK and mark outputs accordingly.

### Known Issues (Post-PR Expectations)
- RSS feeds may rate-limit (403/406/420/429). Expected: summarized failure report, scanner completes.
- IBKR error 300/321 may occur. Expected: logged per symbol, scanner continues.
- Watchlist may be empty. Expected: file header + exclusion reason summary.

### How to Run
- Orchestrator:
  - `python -m src.main`
- Standalone scanner_runner:
  - `python -m src.scanner.scanner_runner`
  - `python src/scanner/scanner_runner.py`

### Outputs
- Watchlists: `output/watchlists/watchlist_RossMomentum_<timestamp>.txt`
- Scanner audit artifacts (standalone): `docs/PHASE_24_SCANNER_FIELD_AUDIT.json`, `docs/PHASE_24_SCANNER_MECHANICAL_CHECKLIST.md`

### Phase 24 Acceptance Criteria
- scanner_runner executes in module and script modes without ImportError.
- Symbol cap resolution is logged (TOP_GAINERS_COUNT, IBKR_MAX_SYMBOLS_PER_CYCLE, final limit).
- Watchlist output is observable, never silently empty.
- RSS failures are summarized; news is non-blocking.
- IBKR read-only errors are handled per symbol; MOCK fallback works.
- verified_rss.txt exists only at repo root.
