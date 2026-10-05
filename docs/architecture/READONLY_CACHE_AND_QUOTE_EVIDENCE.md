# READ_ONLY cache isolation and quote evidence

The bounded October 5 diagnostic configured SCANNER_FLOAT_CACHE_FILE but scanner_runner._resolve_float_cache_path used a hardcoded operational path. The resolver now reads canonical configuration, retaining data/reference/float_cache.json as the default. Bootstrap and foreground discovery use that path. FloatProvider also obtains its omitted JSON path from canonical configuration, covering the IBKR provider fallback. In-memory cache identity includes resolved path as well as mtime, preventing leakage between same-mtime or missing files.

Float discovery also persists symbol_fundamentals in SQLite. A private isolated run must set **both** SCANNER_FLOAT_CACHE_FILE and PERSISTENCE_SQLITE_PATH. Their defaults remain unchanged; changing only JSON is not whole-store isolation. Discovery workers are keyed by resolved JSON and SQLite paths and pin both paths at construction. The existing private next_readonly_capture.py now supplies a run-local runtime.sqlite3 in addition to its run-local float JSON and news cache. No live run was repeated.

The canonical PR1040 observation now forwards diagnostics.market_data_observations verbatim through market_data_observation_diagnostics.market_data_observations. All evaluated candidates survive, including rejected candidates. Scanner summaries include quality flags alongside confirmed/requested type, market timestamps, receipt/type-callback times, request ID, completion and snapshot evidence. Missing diagnostics stay empty; missing timestamps remain null. Receipt or cycle timestamps are never substituted for market time.

Offline regressions exercise the real resolver/bootstrap/discovery persistence with network discovery stubbed, assert operational JSON/SQLite sentinels remain byte-identical, and cover path changes within one process. Quote regressions cover complete and unavailable metadata plus rejected rows. Existing capture artifacts are not rewritten, and the accidental operational float entry is preserved.

MI's saved RSS evidence shows cache miss, no prep reuse, zero retained matches, transport failures and exhausted tier deadlines. Parsed feed-item counts and actual full issuer identity were not retained; the October 5 raw scanner payload was not found in saved capture directories, older trade-store rows or operational SQLite. Therefore no news matching/scheduling repair is justified from that capture alone. No budgets, relevance rules, catalyst gates or provider defaults change; Massive remains outside Ross.

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL

Multiple FloatProvider instances in the single runtime merge the latest disk state under a shared per-path lock and publish JSON atomically. Sequential stale instances and concurrent worker/provider discoveries retain each other’s records. This is in-process coordination, not a claim of cross-process file locking; the operational preflight still excludes competing runtimes.


## Explainable next news observation

Canonical retrieval diagnostics retain the supplied candidate symbol, company name,
aliases, exchange, market, region and an explicit issuer-ID allowlist. They also
record the RSS matcher’s normalized company aliases using the adapter’s actual
metadata precedence. Missing names remain null; no lookup enriches this record.
Arbitrary metadata, headlines, payloads and credentials are excluded. These
identity records describe request inputs, including empty and cache-only results;
they do not establish that a source matched the issuer.

Ordinary RSS diagnostics now retain parsed `feed_item_count` and coordinator-observed
`worker_completed`, without requiring the optional lifecycle collector. Feed size
is measured before relevance/publication filtering and is separate from matched
count. A known empty feed is zero, while missing/failed/unobserved feeds remain
null. Existing request/parse/HTTP/cleanup measurements are forwarded when available;
unmeasured ordinary-call timings remain null. The worker completion timestamp,
deadline decisions and late-result eligibility are unchanged.

The private capture runs from its newly created output directory, with the reviewed
repository on `PYTHONPATH`. Explicit absolute news/float/SQLite destinations remain
run-local; default relative reference and prep paths resolve beneath that same
working directory. Offline tests reach all five stores and compare operational
sentinels byte for byte. The earlier altered operational reference cache is retained
as historical evidence, without a guessed restoration. The wrapper remains a
future operator command; no new market or provider observation was performed.
