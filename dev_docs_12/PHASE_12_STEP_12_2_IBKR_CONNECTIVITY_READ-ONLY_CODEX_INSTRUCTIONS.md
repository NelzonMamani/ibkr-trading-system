PHASE_12_STEP_12_2_IBKR_CONNECTIVITY_READ-ONLY_CODEX_INSTRUCTIONS.md 
PHASE 12 · STEP 12.2 — IBKR CONNECTIVITY (READ-ONLY) — CODEX INSTRUCTIONS (SINGLE BLOCK)

OBJECTIVE
Implement a READ-ONLY IBKR adapter layer that proves:
1) We can connect/disconnect to IBKR safely
2) We can resolve contracts (symbol → conId)
3) We can fetch a market data snapshot (bid/ask/last) in a controlled way
4) We can expose a health/heartbeat status
WITHOUT placing or managing ANY live orders.

NON-NEGOTIABLE SAFETY RULES
- No order placement APIs may be called in this step (no placeOrder, no whatIfOrder).
- No “paper trading” execution in this step.
- LIVE run mode is permitted ONLY to test connectivity + read market data.
- All read-only IBKR calls must be behind explicit config gating: IBKR_READONLY_ENABLED=true.
- Any attempt to route/submit an order through the IBKR path in this step MUST hard fail with a clear error.

DELIVERABLES (FILES / MODULES)
Create or update the following files. If a file already exists, modify it rather than duplicating.

1) src/adapters/brokers/ibkr/ibkr_client.py
   - A thin client wrapper around the official Interactive Brokers Python API (ibapi).
   - Responsibilities:
     - connect() / disconnect()
     - is_connected() / health()
     - resolve_contract(symbol, exchange="SMART", currency="USD") -> ContractDetails-like result (store conId)
     - get_market_snapshot(symbol) -> MarketSnapshot (bid/ask/last/timestamp)
   - Must be read-only: no order methods exposed.

2) src/adapters/brokers/ibkr/ibkr_broker.py
   - A broker adapter implementing your system’s Broker interface (or equivalent abstraction).
   - Responsibilities:
     - expose the read-only methods (resolve_contract, get_market_snapshot, health)
     - for any order-related method in the broker interface (submit/cancel/replace/etc):
       raise RuntimeError("IBKR READ-ONLY MODE: order submission disabled in Phase 12.2")

3) src/domain/models/market_snapshot.py  (or wherever your domain models live)
   - Dataclass: MarketSnapshot
     fields:
       - symbol: str
       - bid: float | None
       - ask: float | None
       - last: float | None
       - asof_utc: datetime
       - source: str = "IBKR"

4) src/config/runtime_config.py (or your config module)
   - Add config values:
     - IBKR_READONLY_ENABLED: bool (default False)
     - IBKR_HOST: str (default "127.0.0.1")
     - IBKR_PORT: int (default 7497)  # TWS paper default; allow override
     - IBKR_CLIENT_ID: int (default 7) # allow override
     - IBKR_SNAPSHOT_TIMEOUT_SECONDS: int (default 5)
     - IBKR_MARKET_DATA_TYPE: str (default "LIVE") # or "DELAYED" depending on availability; do not assume
   - Ensure these appear in the “[CONFIG] Resolved runtime configuration” section of your boot logs.

5) src/main.py (or orchestrator boot path)
   - Add a “READ-ONLY IBKR smoke test” path that runs only when:
     RUN_MODE in {SIM, LIVE} AND IBKR_READONLY_ENABLED=true AND a symbol is provided
   - The smoke test should:
     - connect to IBKR
     - resolve contract for a single symbol
     - request a market snapshot for that symbol
     - log the snapshot result clearly
     - disconnect cleanly
   - This must NOT affect the existing teaching pipeline unless the flag is enabled.

6) tests/test_ibkr_readonly.py (or similar)
   - Unit tests that do not require a live IBKR connection:
     - verify that order-related methods hard-fail in read-only mode
     - verify MarketSnapshot validation / formatting
   - Integration tests are optional but if present must be skipped by default unless an env var is set.

IMPLEMENTATION DETAILS (IMPORTANT)
A) Use ibapi (IB’s official API) pattern
- Implement an EWrapper/EClient subclass combo.
- Run the IB network loop in a background thread:
  - client = IbkrClient(...)
  - client.connect()
  - start thread to call client.run() (or EClient.run)
  - ensure disconnect stops the loop gracefully

B) Request/response correlation
- Maintain an internal request id counter.
- For contract resolution:
  - use reqContractDetails(reqId, contract)
  - collect results in a dict keyed by reqId
  - signal completion when contractDetailsEnd(reqId) fires
- For market snapshot:
  - use reqMktData(reqId, contract, "", snapshot=True, regulatorySnapshot=False, mktDataOptions=[])
  - capture tickPrice callbacks:
    - bid/ask/last ticks
  - when you have at least one price OR timeout occurs, cancelMktData(reqId) (safe even for snapshot)
  - return MarketSnapshot with whatever you got (None if missing)

C) Timeouts and thread safety
- Use threading.Event or queue.Queue to wait for completion with a timeout:
  - contract_details_event.wait(timeout)
  - market_data_event.wait(timeout)
- Protect shared dicts with a lock.

D) Logging discipline
- Every IBKR action must log:
  - connect attempt + host/port/client_id
  - connection status
  - reqId for each request
  - resolved conId
  - snapshot result (bid/ask/last)
  - disconnect complete
- Ensure logs are short and readable; do not dump huge IB objects.

E) Failure modes (must be explicit)
- If IBKR_READONLY_ENABLED=false:
  - IbkrClient should not connect; raise RuntimeError("IBKR read-only disabled by config")
- If connection fails:
  - raise RuntimeError with the IB error code/message captured in error(reqId, errorCode, errorString)
- If snapshot times out:
  - return MarketSnapshot with None fields and log a warning (do NOT crash)
- If symbol resolution fails:
  - raise RuntimeError("Contract resolution failed for symbol=...")

CLI / CONFIG USAGE
- Support a simple invocation:
  - env IBKR_READONLY_ENABLED=true
  - optionally IBKR_HOST/PORT/CLIENT_ID
  - optionally a symbol flag like IBKR_SMOKE_SYMBOL=AAPL (or your existing config mechanism)
- The smoke test should run once and exit (not start the continuous teaching loop) if IBKR_SMOKE_SYMBOL is provided.
  - If no symbol is provided, normal behaviour continues.

ACCEPTANCE CHECKLIST
- Running with IBKR_READONLY_ENABLED=false behaves exactly as before (no IBKR activity).
- Running with IBKR_READONLY_ENABLED=true and IBKR_SMOKE_SYMBOL set:
  - connects, resolves contract, prints snapshot, disconnects, exits 0
- Any order submission call path through IbkrBroker raises a RuntimeError and is covered by tests.
- No trading logic changed; this step is connectivity + data only.

END 