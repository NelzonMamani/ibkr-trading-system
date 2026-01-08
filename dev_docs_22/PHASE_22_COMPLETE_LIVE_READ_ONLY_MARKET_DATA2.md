PHASE_22_COMPLETE_LIVE_READ_ONLY_MARKET_DATA2.md
PHASE 22_COMPLETE_LIVE_READ_ONLY_MARKET_DATA.md

CODex INSTRUCTIONS (single block, execute in one PR)

GOAL
Implement PHASE 22: “Complete Live Read-Only Market Data” in the IBKR Trading System, while troubleshooting and fixing any regressions or incomplete work from earlier phases (including Phase 21 normalisation/dedup). Deliver a working, observable, deterministic system that:
- Connects to IBKR in READ-ONLY mode (no orders ever sent to IBKR)
- Pulls LIVE market data (or safe fallback) for a small set of symbols each cycle
- Populates scanner candidates using real market data fields (bid/ask/last/spread/volume etc.)
- Preserves existing teaching-first orchestration, but upgrades Scanner to real read-only market data
- Provides explicit validations and invariant checks at startup, per-cycle, and on shutdown

NON-NEGOTIABLE SAFETY
1) IBKR_READONLY_ENABLED=True must hard-block any broker order placement and any code path that could transmit an order to IBKR.
2) RUN_MODE=SIM remains allowed for internal simulated execution; however, market data fetching must be real (IBKR market data).
3) If any “order placement” API is reachable while IBKR_READONLY_ENABLED=True, fail fast at boot.

SCOPE OF CHANGE
- Implement/upgrade IBKR market data read-only layer (snapshot + optional streaming) and integrate into Scanner.
- Ensure Phase 21 intent normalisation and intent de-duplication are actually in effect and validated.
- Add validations required for Phase 22 and for the earlier “validation-first” requirement.
- Optional: rename database file extension from .sqlite to .db if it is still SQLite, with backward compatibility.

DELIVERABLES (FILES)
A) Create the markdown phase document:
- Create file: docs/phases/PHASE_22_COMPLETE_LIVE_READ_ONLY_MARKET_DATA.md
- Title at top must match filename exactly.
- Include: objective, architecture, config keys, data flow, validations, definition of done, test plan.

B) Code changes in src/
Implement the live read-only market data integration end-to-end:
1) src/ibkr/market_data_client.py (new or upgraded)
   - Provide a MarketDataClient that uses ib_insync (or existing IB layer) to:
     - connect using IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
     - set market data type:
       - if IBKR_MARKET_DATA_TYPE=LIVE -> requestMarketDataType(1)
       - else if DELAYED -> requestMarketDataType(3)
       - else if DELAYED_FROZEN -> requestMarketDataType(4)
     - fetch snapshot market data per symbol with a timeout IBKR_SNAPSHOT_TIMEOUT_SECONDS
     - return a typed result object MarketDataSnapshot:
       fields: symbol, bid, ask, last, last_size, bid_size, ask_size, volume, vwap, high, low, close, open, timestamp, spread, data_quality_flags
     - compute spread if bid and ask exist, else None
     - apply safety: if no data within timeout, return snapshot with data_quality_flags including “MD_TIMEOUT” and None values

2) src/scanner/scanner_live_readonly.py (new)
   - Implement LiveReadOnlyScanner that replaces the “static fake symbols” teaching scanner when enabled.
   - Inputs: config + MarketDataClient + a symbol source (see below)
   - Pipeline per cycle:
     a) Determine symbols to request:
        - Prefer: a fixed configurable list SCANNER_SYMBOLS (comma-separated) if provided
        - Else fallback: a small default list like ["AAPL","TSLA","NVDA","AMD","SPY"] for reliability
        - Cap to IBKR_MAX_SYMBOLS_PER_CYCLE
     b) For each symbol:
        - request snapshot market data (bid/ask/last/volume etc.)
        - build ScannerCandidate using real data:
          - symbol
          - price = last if available else mid(bid/ask) else None
          - bid, ask, spread, volume populated when available
          - session = detected market session
          - data_quality_flags propagated
        - For Phase 22, you do NOT need gap%, rvol, float, news; keep those as None or placeholders, but do not remove fields.
     c) Output candidates list (may be fewer if contract qualification fails)

3) src/scanner/__init__.py and wherever scanner is instantiated
   - Add a config toggle: SCANNER_MODE = "TEACHING" | "LIVE_READONLY"
   - Default remains TEACHING to preserve Phase 4, but Phase 22 doc should show how to enable LIVE_READONLY.
   - In main boot, if SCANNER_MODE=LIVE_READONLY:
     - instantiate MarketDataClient
     - instantiate LiveReadOnlyScanner
     - log clearly:
       [SCAN] LiveReadOnlyScanner enabled — using IBKR read-only market data

4) Contract qualification
   - In MarketDataClient, qualify contracts for US stocks:
     - Stock(symbol, "SMART", "USD") and ib.qualifyContracts
   - If qualification fails:
     - produce data_quality_flags “CONTRACT_QUALIFY_FAILED”
     - do not crash

C) Phase 21 verification and fixes (must be real)
1) Intent normalisation / dedup stage must exist as a named stage in orchestrator pipeline:
   - After StrategyRunner aggregates TradeIntents and before RiskEngine runs.
   - It must deduplicate by (symbol, trader_type, direction) keeping highest confidence.
   - It must emit events:
     - INTENT_NORMALISED with before/after counts
     - INTENT_DROPPED_DUPLICATE for each dropped intent (with rationale)
2) Validation must prove dedup is working:
   - Per cycle log:
     [INTENT][VALIDATION] Deduplication OK — before=<n> after=<m> duplicates_dropped=<k>
   - If duplicates remain after normalisation: fail fast (raise RuntimeError) and stop cycle.

D) Read-only enforcement (hard guard)
1) Add a central guard utility, e.g. src/ibkr/read_only_guard.py
   - function assert_read_only_allows(action: str)
   - If IBKR_READONLY_ENABLED=True and action in ["PLACE_ORDER","MODIFY_ORDER","CANCEL_ORDER"]:
     raise RuntimeError("Read-only enabled: blocking broker action ...")
2) Ensure any IBKR execution adapter calls this guard before any order API.
3) At boot, run a “guard self-test”:
   - Attempt a mocked “PLACE_ORDER” action and confirm it raises.
   - Log:
     [CONFIG][VALIDATION] Read-only guard enforced

E) Storage file extension rename (optional but requested)
1) If current DB path ends with ibkr_system.sqlite, change default to ibkr_system.db.
2) Backward compatible:
   - If .db does not exist but .sqlite exists, use .sqlite and log a warning:
     [STORAGE][WARN] Using legacy sqlite filename ibkr_system.sqlite; consider renaming to ibkr_system.db
3) Update logs to say:
   [STORAGE] SQLite path resolved to <...ibkr_system.db or .sqlite>

F) Validation framework (required)
Implement explicit validations that were “supposed to be validated”:
1) Startup validations (fail fast):
   - Config resolved
   - DB opens
   - IBKR connection succeeds if SCANNER_MODE=LIVE_READONLY
   - Market data type request executed and logged
2) Per-cycle validations:
   - Event counts consistent with persisted count
   - No duplicate intents after normalisation
   - No active trades remain after shutdown
3) End-of-cycle validation summary log:
   [VALIDATION][SUMMARY] storage=OK intent=OK market_data=OK events=OK
   If any is not OK => raise RuntimeError

G) Logging requirements (observability)
- Market data log per symbol (single line, concise):
  [MD] symbol=NVDA bid=... ask=... last=... spread=... vol=... flags=[...]
- Scanner output log:
  [SCAN] produced candidates=<n> mode=LIVE_READONLY
- If market data is missing:
  [MD][WARN] symbol=... timeout or missing fields flags=[MD_TIMEOUT,...]

TEST PLAN (must be included in doc + runnable steps)
1) TEACHING mode still works:
   - SCANNER_MODE=TEACHING, run main.py, verify it behaves like current output and no crashes.
2) LIVE_READONLY mode:
   - Set IBKR_READONLY_ENABLED=True
   - Set SCANNER_MODE=LIVE_READONLY
   - Set IBKR_PORT=7497 for paper trading TWS/IB Gateway as user already uses
   - Run main.py
   - Verify:
     - IBKR connects
     - Market data type set to LIVE (or fallback)
     - Candidates contain real bid/ask/last where available
     - No broker orders attempted; guard validation prints OK
3) Shut down with Ctrl+C:
   - Verify graceful shutdown closes any simulated trades and registry verification passes.

DEFINITION OF DONE (must be satisfied)
- In LIVE_READONLY mode, the scanner uses IBKR read-only market data and prints real bid/ask/last/spread/volume for at least 1 symbol (when market is open and subscription exists).
- No broker order API can be reached while IBKR_READONLY_ENABLED=True (guard enforced + boot self-test).
- Intent normalisation/dedup is present, emits events, and validation proves no duplicates remain.
- End-of-cycle validation summary prints all OK.
- System shuts down leaving zero active trades and logs registry verification passed.

OUTPUT REQUIRED FROM CODEX
- Provide a PR implementing all above.
- Include the new docs/phases/PHASE_22_COMPLETE_LIVE_READ_ONLY_MARKET_DATA.md file.
- Ensure imports and packaging are correct and main.py runs.

END_WORD
END_WORD