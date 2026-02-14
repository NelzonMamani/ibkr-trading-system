# IBKR Trading System — System Architecture

**Status:** LOCKED (authoritative)

This document defines the runtime architecture, component responsibilities, and guardrail behaviour for the IBKR Trading System.

## A. Architectural axioms

1. **Single source of truth for decisions**
   - The **scanner** produces facts/measurements only.
   - The **strategy policy** consumes facts and decides (trade/no‑trade, sizing, stops, targets).
   - The **orchestrator** routes data and enforces mode/guardrails; it does not invent trading logic.

2. **One connection, shared by all components**
   - A single IBKR session (host/port/clientId) is established and owned by a connection layer.
   - Market data, scanner, and execution must reuse that session. No “side connections”.

3. **Mode is authoritative and centrally enforced**
   - Runtime mode is resolved exactly once at boot.
   - Every component can query the resolved mode but cannot override it.
   - Mode determines what is permitted (e.g., placing orders) and what is simulated.

4. **Explicit lifecycle**
   - Boot → preflight → connect → warmup/snapshots → scan → watchlist → focus → strategy loop → risk → execution (or simulated execution).

5. **Deterministic observability**
   - Every cycle prints (or logs) enough structured information to explain:
     - what universe was scanned,
     - what was excluded (and why),
     - what made it into watchlist and focus,
     - and what the strategy decided.

---

## B. Component map

### 1) Boot & Configuration

**ConfigRegistry / RuntimeConfigResolver**
- Reads environment variables and config files.
- Produces an immutable `RuntimeConfig` object.
- Enforces “hard” constraints (for example: disallow replay modes in LIVE).
- Emits a config summary (what is forced, what is optional, and the final resolved values).

**Key output contract**
- `RUN_MODE` is resolved to one of the supported modes (see section D).
- `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID` resolved (or client ID chosen deterministically).

### 2) Connection layer

**IBKRConnectionManager (single owner of IB API session)**
Responsibilities:
- Establish/maintain a single TWS/IB Gateway connection.
- Apply safe defaults (timeouts, retries, rate limiting).
- Expose a thread‑safe “connected client” to downstream components.
- Provide connection health checks (isConnected, last heartbeat).

Must prevent the operator pain you described:
- When the system starts, it should not die due to an old/stale clientId or a left‑open socket without giving an actionable message and a deterministic recovery path.

**Recommended behaviour**
- On connect failure, classify the error:
  - wrong host/port
  - gateway not running
  - clientId already in use
  - API permissions mismatch
  - network timeout
- For “clientId in use”, auto‑retry with a new clientId in a controlled range (configurable) and print the final chosen clientId.

### 3) Market data layer

**MarketDataClient**
Responsibilities:
- Provide snapshots (last/close/volume/bid/ask/spread) for a list of contracts.
- Handle contract qualification asynchronously.
- Enforce snapshot completeness rules (wait for last/close/volume where required).
- Provide normalized values and missing‑data flags.

**Contract**
- Strategy runner and scanner operate on qualified contracts. Qualification is not optional.

### 4) Scanner layer

**ScannerRunner**
Responsibilities:
- Pull “top N gainers” (or other IBKR scan codes).
- Produce a list of scan result objects containing:
  - symbol, conId, exchange
  - last, close, previous close reference used
  - percent change (as computed and as IBKR provides, where applicable)
  - volume, bid, ask, spread
  - data quality flags
- Apply only “mechanical” filtering (e.g., remove obvious invalid rows, missing symbol, missing conId).

**ScannerPolicy (mechanical / non‑strategic)**
- Defines the scanning universe size (N=50) and the raw fields to collect.
- Does not apply Ross 5‑pillar decisions. Those live in the strategy policy.

### 5) Orchestrator layer

**Orchestrator**
Responsibilities:
- Own the cycle loop and the “pipeline order”.
- Call scanner → ask market data for snapshots → pass results to strategy policy.
- Enforce mode permissions:
  - In LIVE_READ_ONLY and SIM, it must never place orders.
  - In LIVE_MICRO / LIVE_1_SHARE, it must hard cap size.
- Perform structured printing/logging.

### 6) Strategy layer

**StrategyRunner**
Responsibilities:
- Provide a stable adapter around a strategy module.
- Standardise inputs (market snapshot facts, time, mode, account state) and outputs (orders/intents).

**StrategyPolicy (per strategy)**
Responsibilities:
- Consume scan facts and snapshots.
- Apply strategy‑specific gating and ranking.
- Produce:
  - watchlist (target ~15)
  - focus list (target ~3–5)
  - trade intents (0..k)

### 7) Risk layer

**RiskEngine / RiskManager**
Responsibilities:
- Apply portfolio‑level rules (max loss/day, max position size, max trades, correlation limits).
- Translate trade intents into executable orders (or reject with reason).

### 8) Execution layer

**ExecutionGateway**
Responsibilities:
- Place orders when mode allows.
- Provide paper/live execution routing.
- Provide acknowledgements and order state updates to the orchestrator.

---

## C. Runtime pipeline (per cycle)

1. **Preflight**
   - Resolve mode.
   - Validate config.
   - Validate IBKR target (host/port).

2. **Connect**
   - ConnectionManager connects and reports chosen clientId.

3. **Warmup**
   - Qualify contracts and fetch first snapshots.

4. **Scan**
   - ScannerRunner fetches top N gainers.

5. **Snapshot enrichment**
   - MarketDataClient fetches snapshots for scan candidates.

6. **Strategy decision**
   - StrategyPolicy produces watchlist (~15) and focus (~3–5).

7. **Risk and execution**
   - RiskEngine approves/rejects.
   - ExecutionGateway executes only if mode permits.

8. **Audit/prints**
   - Print tables for:
     - top N raw scan rows
     - top 15 watchlist survivors
     - focus list
     - drop reasons summary

---

## D. Supported modes (authoritative)

Modes must be represented as a closed enum and the permissions must be enforced centrally.

| Mode | Scanner | Market Data | Strategy decisions | Orders | Sizing cap |
|---|---|---|---|---|---|
| SIM | yes | simulated or live snapshots (configurable) | yes | simulated only | n/a |
| PAPER | yes | live | yes | paper orders | configured |
| READ_ONLY | yes | live | yes | **no** | n/a |
| LIVE | yes | live | yes | live orders (when EXECUTION_ENABLED=true) | risk profile may enforce micro cap |

Rules:
- LIVE and READ_ONLY must force event replay OFF.
- READ_ONLY must behave like LIVE in data collection, but never place orders.

---

## E. The “I can’t watch this all day” problem: what the system must do

### 1) Deterministic startup
At startup, the system must reach a stable state or fail fast with a clear remedy.

Minimum expectations:
- If IBKR is not reachable: print “Gateway not reachable” and exit non‑zero.
- If clientId is in use: auto‑retry with a new clientId (within a configured range) and continue.
- If a required env var is invalid: print the exact name and expected format.

### 2) “Remove item env before it begins” is not the right solution
Environment variables are not a reliable runtime state mechanism. Instead:
- Use a ConnectionManager that owns connection state.
- Use a lock file or deterministic clientId selection to avoid collisions.

### 3) Health supervision
Add a lightweight supervisor loop:
- If disconnected mid‑run, attempt reconnect N times.
- If reconnect fails, exit with a single actionable error.

---

## F. Recommended “manager” classes (what to have a good grip of the system)

These are the significant controllers that make the system manageable and debuggable:

1. **RuntimeConfigResolver** — resolves the authoritative mode and configuration.
2. **IBKRConnectionManager** — owns the single IB session and reconnection logic.
3. **MarketDataClient** — snapshots, qualification, completeness waiting.
4. **ScannerRunner** — fetches top N, produces facts.
5. **Orchestrator** — pipeline control, mode enforcement, observability.
6. **StrategyRunner** — stable adapter for strategy modules.
7. **RiskEngine** — global risk checks and order shaping.
8. **ExecutionGateway** — the only place orders can be placed.

Optional but useful later:
- **SessionStateStore** (persist daily state: max loss hit, bans, last watchlist).
- **DiagnosticsReporter** (writes structured JSON/CSV for analysis).

---

## G. Naming conventions

Prefer names that describe responsibilities, not layers.

Good:
- ConnectionManager, MarketDataClient, ScannerRunner, StrategyPolicy, RiskEngine, ExecutionGateway

Avoid vague names:
- Handler, Processor, Util, Helper (unless scoped and private)

---

## H. Acceptance criteria (architecture)

The architecture is considered correct when:
- Mode permissions are enforced and verifiable.
- Only one IBKR connection exists.
- Scanner outputs a consistent watchlist (15) or explicitly reports “empty watchlist” as valid.
- A single command can run each mode (root scripts).
- The operator can read the prints and understand drop reasons.


### 4) Scanner layer

**ScannerRunner / ScannerProvider (mechanical only)**
Responsibilities:
- Pull the raw IBKR scanner list (e.g., Top % Gainers, cap 50).
- For each symbol/contract, collect the **minimal measurement set** needed by strategies.
- Output a list of `ScannerObservation` records (facts) in the same order as ranking criteria.

**Scanner MUST NOT**
- Decide “good/bad” for Ross patterns.
- Apply “news gating” logic beyond mechanical availability flags.
- Mutate watchlist/focus sizes except by configured caps.

**Scanner SHOULD**
- Attach computed/observed fields that are required for visibility and later policy decisions, such as:
  - last price
  - prior close reference used
  - percent change (and which reference it used)
  - RVOL proxy used + time window
  - volume, dollar volume, spread, liquidity proxy
  - halts/SSR flags if available
  - data quality flags (missing values, stale snapshots)

### 5) Orchestration layer

**Orchestrator (traffic controller)**
Responsibilities:
- Own the cycle loop.
- Call scanner → take watchlist output → request snapshots → dispatch to strategy runner.
- Enforce **mode guardrails** and safe shutdown.
- Provide structured logs and “drop reasons” at each stage.

Orchestrator stages per cycle:
1. Resolve runtime mode and config (once).
2. Ensure IBKR connection is healthy (or fail fast with clear instruction).
3. Scanner run (Top N).
4. Snapshot enrichment for the survivors.
5. Strategy runner execution (policy decides).
6. Risk engine enforces risk rules.
7. Execution router places orders (or simulates).
8. Persist telemetry (optional) and sleep.

### 6) Strategy layer

**StrategyRunner (executor of a strategy module)**
Responsibilities:
- Load a strategy module by name.
- Validate inputs (observations + snapshots) match the module’s contract.
- Call `strategy_policy.evaluate(...)` and receive a `DecisionSet`.
- Emit structured decision logs.

**StrategyPolicy (the brain)**
Responsibilities:
- Consume facts and decide.
- Own the stock‑selection gates that are “meaningful” (Ross 5 pillars, pattern library, risk overlays).
- Produce explicit reasons for each drop.

### 7) Risk layer

**RiskEngine (governor)**
Responsibilities:
- Enforce system‑level risk (max daily loss, max positions, max exposure, stop trading triggers).
- Enforce per‑trade constraints (max size, min RR, stop distance, slippage assumptions).
- Provide “deny with reason” decisions described in logs.

### 8) Execution layer

**ExecutionRouter (mode‑aware order interface)**
Responsibilities:
- Convert decisions into orders.
- In non‑live modes, **never** send orders to IBKR; simulate fills.
- In live modes, route orders to IBKR using the shared connection.

### 9) Learning / Analytics layer (optional, non‑blocking)

**LearningManager (offline by default)**
Responsibilities:
- Subscribe to telemetry and trade outcomes.
- Produce metrics and reports.
- Must not block live trading.

If present, it is a consumer, not a controller.

---

## C. Data contracts

### ScannerObservation (facts)
Minimum fields (extendable):
- symbol, exchange, primaryExchange, currency
- qualifiedContractId
- last, close, previousCloseUsed
- pctChange, pctChangeMethod
- volume, avgVolumeProxy, rvolProxy
- bid, ask, spread, spreadBps
- dollarVolume
- haltFlag, ssrFlag (if available)
- dataQuality: { missing_last, missing_close, stale_snapshot, ... }

### DecisionSet
- actions: list of {symbol, side, qty, entryType, stop, target, timeInForce, rationale}
- drops: list of {symbol, stage, reasonCode, details}
- diagnostics: policy stats for the cycle

---

## D. Runtime modes (authoritative)

The system supports these modes. Mode is resolved once and then enforced everywhere.

| Mode | Market data | Scanner | Orders | Position sizing | Intended use |
|---|---|---|---|---|---|
| SIM | Simulated | Simulated or live data (config) | Simulated | Full sizing | backtests / dry runs |
| PAPER | Live market data | Live scanner | Sent to paper account | Full sizing | paper trading |
| LIVE_READ_ONLY | Live market data | Live scanner | **Blocked** | N/A | observe only |
| LIVE_MICRO | Live market data | Live scanner | Allowed | **force 1 share or tiny sizing** | production smoke test |
| LIVE | Live market data | Live scanner | Allowed | Full sizing | production |

**LIVE 1 SHARE**
- Treat as an alias of LIVE_MICRO if you prefer the naming, but only one should exist in code.

Mode guardrails:
- In LIVE_READ_ONLY, any attempt to place an order is a hard error with a clear message.
- In LIVE_MICRO, the router clamps size to 1 share (or config minimum) regardless of policy sizing.

---

## E. Startup and recovery behaviour (operator quality of life)

You said: “I can’t run the system and pay attention all day.”
So startup must be deterministic and self‑healing within safe boundaries.

### 1) ClientId / stale connection pain
Typical failure: “clientId already in use” because the previous run crashed or TWS still holds it.

**Required behaviour**
- If `IBKR_CLIENT_ID` is provided explicitly, try it first.
- If connection fails with “clientId in use”, retry using `IBKR_CLIENT_ID + k` for k=1..K (K configurable, default 10).
- Print a single summary line with the final chosen clientId.
- Persist the chosen clientId in the process logs only (do not write to repo files).

### 2) Remove‑item env idea
Removing env vars at runtime is not the right control plane.
Instead:
- Provide a single `RuntimeConfigResolver` that resolves mode and connection settings.
- Provide wrapper scripts (one per mode) so you never hand‑edit env vars.

### 3) Preflight checks
Before the cycle loop begins:
- Check IBKR host/port reachable.
- Check gateway session is logged in.
- Check API settings allow connections.
- Validate market data permissions if possible (or degrade with explicit warning).

### 4) Shutdown behaviour
- Capture SIGINT/SIGTERM.
- Cancel outstanding subscriptions.
- Disconnect gracefully.

---

## F. What must be visible in logs

Per cycle, the operator should see:
- resolved mode
- chosen clientId
- Top N raw scanner output count
- Watchlist count (15) and the list of symbols
- Focus list count (3–5) and the list of symbols
- Drop reasons aggregated by reason code
- Strategy decisions summary (trades attempted / blocked by mode / denied by risk)

If any value is missing due to market closed / after hours:
- print the method used (reference close, previous close, last trade, frozen value) and flag it as such.


### 5) Orchestration layer

**Orchestrator (router + governance enforcer)**
Responsibilities:
- Own the single runtime cycle:
  1) ask scanner for observations,
  2) log/print diagnostics,
  3) pass observations to the chosen strategy policy,
  4) if strategy outputs “candidates”, request market-data snapshots,
  5) hand the enriched packet to the strategy runner (pattern/entry logic),
  6) if and only if in a live-trading allowed mode, submit orders.
- Enforce mode guardrails (Section C).
- Enforce cycle timing and safe shutdown.

### 6) Strategy layer

**StrategyPolicy (decision brain)**
Responsibilities:
- Consume `ScannerObservation` (facts) and decide watchlist / focus list / trade candidates.
- Provide explicit, debuggable drop reasons.
- Provide per-mode behaviour (e.g., allow training/logging while blocking orders).

**StrategyRunner (execution logic but still not the broker)**
Responsibilities:
- Convert policy decisions into concrete entry/exit plans.
- Compute pattern signals from candles/snapshots.
- Send “intents” to the Execution layer.

### 7) Execution layer

**ExecutionEngine / OrderExecutor**
Responsibilities:
- Convert intents to broker orders.
- Enforce risk constraints from RiskEngine.
- Support paper/sim/live routing.
- Confirm fills and produce execution events.

### 8) Risk layer

**RiskEngine**
Responsibilities:
- Central risk checks: max loss, max position, max orders, kill-switch.
- Mode-specific hard stops:
  - LIVE_READ_ONLY / SIM / PAPER: no broker orders.
  - LIVE_MICRO / LIVE_ONE_SHARE: enforce the micro sizing contract.

### 9) Learning / Research layer (optional but supported)

**LearningManager (offline and read-only by default)**
Responsibilities:
- Collect features, decisions, outcomes.
- Run backtests or post-trade analysis.
- Never able to place orders directly.


### 2) Connection self-healing (clientId / stale sessions)

**Problem pattern**
- TWS/Gateway keeps a session open.
- Your process restarts and reuses the same `clientId`.
- IBKR refuses the connection (or you get partial data behaviour).

**Authoritative solution**
- Never rely on “removing an env var before begin”. Environment cleanup is not a real recovery mechanism.
- Implement a connection strategy that is robust **even if the operator does nothing**:
  1) try the requested clientId (from env/config),
  2) if IBKR rejects due to clientId conflict, automatically probe the next IDs in a small safe range (e.g., 40..60) until connect succeeds,
  3) print the final chosen clientId and persist it to a local runtime file (optional) so subsequent runs can reuse the last known good ID.

**Guardrails**
- Never attempt unlimited retries.
- Always print a single-line “next action” if it cannot connect.

### 3) Watchlist observability as a contract

Every cycle must end with an explicit line that shows:
- `WATCHLIST_COUNT=<n>` and the list of symbols (or IDs), and
- `FOCUS_COUNT=<m>` and the list.

This prevents “silent failure” where the system is running but producing nothing.

---

## F. Optional module: Learning / Research

There may or may not be a learning subsystem. If it exists, it must be isolated:

**LearningManager (offline or shadow mode only)**
- Collects features and outcomes.
- Trains or evaluates models.
- Can propose parameter updates.

**Hard rule**
- Learning cannot change live trading behaviour unless a human explicitly promotes a versioned parameter set (governance).

---

## G. Canonical manager/controller list (what to "have a grip")

These are the “significant classes” that should exist as first-class citizens:

1. `RuntimeConfigResolver` (mode authority)
2. `IBKRConnectionManager` (single IB session)
3. `MarketDataClient` (snapshots + qualification)
4. `ScannerRunner` (facts only)
5. `Orchestrator` (pipeline + routing)
6. `StrategyPolicy` (decision brain)
7. `StrategyRunner` (adapter)
8. `RiskManager` (portfolio guardrails)
9. `ExecutionGateway` (orders)
10. `TelemetryLogger` (structured prints/logs)

If you want only one “startup manager”, it is the **Orchestrator**, but it should be thin and delegate to the above.
