FILE NAME:
PHASE_22_COMPLETE_LIVE_READ_ONLY_MARKET_DATA.md

TITLE:
PHASE 22 — Live Read-Only Market Data Integration (IBKR)

OBJECTIVE:
Introduce real Interactive Brokers market data into the system in a strictly
READ-ONLY, NON-TRADING manner, replacing teaching placeholders while preserving
all safety guarantees, determinism controls, and replay integrity.

This phase transitions the system from “conceptual data” to “real data” without
allowing order execution against live markets.

SCOPE:
- Scanner
- Market data adapters
- Price feeds used by PatternEngine, SignalEngine, and ExecutionEngine (pricing only)
- Configuration and safety gating

NO changes to:
- Strategy logic
- Risk logic
- Execution routing (must remain blocked)
- Persistence schema

---

IMPLEMENTATION REQUIREMENTS:

1. READ-ONLY GUARANTEE (HARD RULE)
   - Introduce a global configuration gate:
     IBKR_READONLY_ENABLED = True
   - When enabled:
     - Market data requests ARE allowed
     - Order placement MUST be blocked at the final gateway
   - Any attempt to submit an order while READONLY is enabled must:
     - Be rejected
     - Emit an explicit safety event

2. MARKET DATA SOURCE INTEGRATION
   - Replace teaching/static prices with live IBKR data for:
     - Last trade price
     - Bid / ask
     - Spread
     - Volume (where available)
   - Support:
     - Snapshot requests
     - Delayed-frozen data (where live is unavailable)
   - Clearly log which data mode is active:
     LIVE | DELAYED | SNAPSHOT | FALLBACK

3. SCANNER REALISM (READ-ONLY)
   - Scanner must:
     - Query IBKR for symbols (or accept an external watchlist)
     - Populate ScannerCandidate fields from live data
   - If IBKR is unavailable:
     - Gracefully fall back to teaching/static mode
     - Emit a warning event

4. EXECUTION ENGINE SAFETY INTERLOCK
   - ExecutionEngine must detect READONLY mode
   - Instead of routing orders:
     - Emit ORDER_BLOCKED_READONLY event
     - Return ExecutionResult with status=BLOCKED
   - This applies even if RiskEngine allows the trade

5. EVENT MODEL EXTENSION (NO SCHEMA BREAK)
   Add new event types (reusing existing event table):
   - MARKET_DATA_CONNECTED
   - MARKET_DATA_SNAPSHOT
   - MARKET_DATA_FALLBACK
   - ORDER_BLOCKED_READONLY

6. REPLAY & DETERMINISM
   - All live prices used in a cycle MUST be captured as events
   - Replay must:
     - Reconstruct identical prices
     - Produce identical downstream decisions
   - No hidden external calls during replay

7. CONFIGURATION SURFACE
   Introduce or confirm:
   - IBKR_READONLY_ENABLED (True by default)
   - IBKR_MARKET_DATA_TYPE (LIVE | DELAYED)
   - IBKR_SNAPSHOT_TIMEOUT_SECONDS
   - IBKR_MAX_SYMBOLS_PER_CYCLE

8. LOGGING & TEACHING CLARITY
   - Logs must explicitly state:
     - “LIVE DATA — READ ONLY MODE”
     - “NO ORDERS WILL BE SENT”
   - Any blocked execution must explain WHY it was blocked

---

EXPECTED OUTCOME:

- System runs end-to-end using REAL IBKR market data
- Scanner, patterns, signals, and strategies operate on live prices
- Execution is fully blocked and safe
- Events and prices are persisted and replayable
- No regression to Phase 20 persistence or replay invariants

---

DEFINITION OF DONE:

- Live IBKR prices visible in logs and persisted events
- No broker orders sent under any circumstance
- ORDER_BLOCKED_READONLY events present in SQLite
- Replay reproduces identical prices and decisions
- System can run during market hours without risk

END