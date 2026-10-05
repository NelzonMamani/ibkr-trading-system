# READ_ONLY cache isolation and quote evidence

The bounded October 5 diagnostic configured SCANNER_FLOAT_CACHE_FILE but scanner_runner._resolve_float_cache_path used a hardcoded operational path. The resolver now reads canonical configuration, retaining data/reference/float_cache.json as the default. Bootstrap and foreground discovery use that path. FloatProvider also obtains its omitted JSON path from canonical configuration, covering the IBKR provider fallback. In-memory cache identity includes resolved path as well as mtime, preventing leakage between same-mtime or missing files.

Float discovery also persists symbol_fundamentals in SQLite. A private isolated run must set **both** SCANNER_FLOAT_CACHE_FILE and PERSISTENCE_SQLITE_PATH. Their defaults remain unchanged; changing only JSON is not whole-store isolation. Discovery workers are keyed by resolved JSON and SQLite paths and pin both paths at construction. The existing private next_readonly_capture.py now supplies a run-local runtime.sqlite3 in addition to its run-local float JSON and news cache. No live run was repeated.

The canonical PR1040 observation now forwards diagnostics.market_data_observations verbatim through market_data_observation_diagnostics.market_data_observations. All evaluated candidates survive, including rejected candidates. Scanner summaries include quality flags alongside confirmed/requested type, market timestamps, receipt/type-callback times, request ID, completion and snapshot evidence. Missing diagnostics stay empty; missing timestamps remain null. Receipt or cycle timestamps are never substituted for market time.

Offline regressions exercise the real resolver/bootstrap/discovery persistence with network discovery stubbed, assert operational JSON/SQLite sentinels remain byte-identical, and cover path changes within one process. Quote regressions cover complete and unavailable metadata plus rejected rows. Existing capture artifacts are not rewritten, and the accidental operational float entry is preserved.

MI's saved RSS evidence shows cache miss, no prep reuse, zero retained matches, transport failures and exhausted tier deadlines. Parsed feed-item counts and actual full issuer identity were not retained; the October 5 raw scanner payload was not found in saved capture directories, older trade-store rows or operational SQLite. Therefore no news matching/scheduling repair is justified from that capture alone. No budgets, relevance rules, catalyst gates or provider defaults change; Massive remains outside Ross.

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL
