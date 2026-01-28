# Codex Implementation Instructions — Managers & Architecture Alignment (LOCKED)

**Goal:** implement the “manager” layer that gives the system a firm grip on runtime safety, connection stability, and mode correctness across: `SIM`, `PAPER`, `LIVE_READ_ONLY`, `LIVE_MICRO`, `LIVE_ONE_SHARE`, `LIVE`.

This doc is written as an actionable checklist. No reinterpretation: follow in order.

---

## 1) Create/confirm the manager layer

### 1.1 RuntimeModeManager (authoritative)
**Purpose:** Resolve mode + enforce guardrails so the rest of the system can be “dumb”.

**Must provide**
- `resolved_mode: RuntimeMode` enum
- `is_live_like` (true for LIVE, LIVE_ONE_SHARE, LIVE_MICRO)
- `allow_orders` (true only in live-like)
- `max_shares_per_order` (1 for LIVE_ONE_SHARE / LIVE_MICRO, else None)
- `event_replay_mode` forced OFF for live-like
- A single `describe()` string used in startup prints

**Inputs** (existing config/env keys as they already exist in repo)
- `RUN_MODE`, `EVENT_REPLAY_MODE`, plus any current live safety flags.

**Hard rules**
- If `allow_orders==false`, execution modules must be impossible to call (guardrail).
- If any conflicting flags are present, fail fast with a human-readable error.

### 1.2 ConnectionManager (IBKR)
**Purpose:** You cannot watch the system all day. The process must autonomously recover from common IBKR connection failures.

**Must provide**
- `connect()` / `disconnect()`
- `ensure_connected()` used at start of each cycle
- `healthcheck()` (lightweight)
- `with_ibkr_session(...)` context or equivalent lifecycle boundary

**Required behaviour**
1. **clientId strategy**
   - Never hardcode a single static clientId.
   - Use a deterministic but collision-resistant choice (e.g., base id + small random jitter), and retry a small range if IBKR rejects the connection.
   - Persist the chosen clientId for the lifetime of the process (don’t change mid-run).

2. **One IBKR app per process**
   - Ensure only one IBKR connection exists and is shared by scanner, market data, and execution.

3. **Fast failure and backoff**
   - On connect failure, retry with exponential backoff (bounded) and clear logging.
   - If still failing, exit with a single clear diagnosis.

4. **No env-var “manual cleanup” as a fix**
   - Env keys can select ports/hosts; they must not be used as a recovery tool.

### 1.3 MarketDataSnapshotManager
**Purpose:** enforce the snapshot contract and eliminate “N/A last/close/volume” timing issues.

**Must provide**
- `get_snapshot(contract) -> Snapshot` that blocks until required fields are present or timeout
- A policy for “required fields per strategy/mode”

**Important:** This must respect and not regress PR #174 (snapshot wait + async contract qualification).

### 1.4 ScannerDiagnosticsManager
**Purpose:** Always print:
- top 50 raw scanner rows with extended columns
- then top 15 selected watchlist with all columns preserved
- plus drop reasons for any removed from top 50

This is for you to troubleshoot without babysitting.

---

## 2) Keep the scanner mechanical

**Contract:** Scanner returns `List[ScannerObservation]` for up to 50 names.

**Observations must include** (as fields, even if some are missing due to data):
- symbol
- contract details (conId if available)
- last price
- previous/close reference used for percent change
- percent change (with explicit reference basis)
- volume, avg volume (if available)
- relative volume (if available)
- bid, ask, spread (absolute and %)
- liquidity proxy (e.g., dollar volume)
- data quality flags (missing fields, stale, snapshot timeout)
- halt/SSR flags if available
- float fields if available (source tags)

**Scanner must not** decide Ross 5-pillar gates. Those live in Ross policy.

---

## 3) Orchestrator flow (authoritative)

At each cycle:
1. `RuntimeModeManager.resolve()`
2. `ConnectionManager.ensure_connected()`
3. `ScannerRunner.run()` -> 50 observations
4. `ScannerDiagnosticsManager.print_top_50(observations)`
5. `RossMomentumPolicy.select_watchlist(observations)` -> 15 (or fewer, including empty)
6. `ScannerDiagnosticsManager.print_watchlist(watchlist)`
7. `MarketDataSnapshotManager.batch_snapshots(watchlist)`
8. `StrategyRunner.process(watchlist + snapshots)`
9. If mode allows orders: execution path; otherwise log “dry-run” result

---

## 4) Mandatory verification commands (Codex must run and report)

From repo root (Windows PowerShell examples; adjust only if needed):

1) Compile
- `python -m compileall -q src`

2) Tests
- `pytest -q`

3) Smoke runs (1 cycle each)
- `python -m src.main --mode SIM --cycles 1 --strategy ross_momentum`
- `python -m src.main --mode PAPER --cycles 1 --strategy ross_momentum`
- `python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy ross_momentum`

If IBKR is available locally, also:
- `python -m src.main --mode LIVE_MICRO --cycles 1 --strategy ross_momentum`

**Pass criteria**
- No crashes.
- ConnectionManager logs chosen clientId and successful connection.
- Scanner prints top 50 with extended columns.
- System prints watchlist length and symbols (or explicit “empty watchlist accepted”).
- Snapshot manager does not produce persistent N/A for last/close/volume without marking data-quality reasons.

If any command fails, Codex must fix and re-run until all pass.

---

## 5) Deliverable

Codex must produce:
- Code changes implementing the managers above.
- Updated/added docs if needed.
- A PR verification report with the exact terminal outputs (or concise excerpts) for the mandatory commands.


### 3.1 Mode matrix smoke runs
Run each once with `--cycles 1` and confirm startup prints show resolved mode + safety gates.

- SIM:
  - `python -m src.main --mode SIM --cycles 1 --strategy ross_momentum`
- PAPER:
  - `python -m src.main --mode PAPER --cycles 1 --strategy ross_momentum`
- LIVE_READ_ONLY:
  - `python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy ross_momentum`
- LIVE_ONE_SHARE:
  - `python -m src.main --mode LIVE_ONE_SHARE --cycles 1 --strategy ross_momentum`
- LIVE_MICRO:
  - `python -m src.main --mode LIVE_MICRO --cycles 1 --strategy ross_momentum`
- LIVE:
  - `python -m src.main --mode LIVE --cycles 1 --strategy ross_momentum`

**Expected**
- All modes start.
- Live-like modes force replay OFF.
- Read-only modes cannot place orders (guardrails verified by code path and tests).
- Scanner prints two tables:
  1) Top 50, extended columns
  2) Top 15 watchlist, same columns preserved

---

## 5) Acceptance criteria (do not merge until all true)

1. A single run produces a watchlist print (can be empty, but must be explicit).
2. Percent-change and reference basis are printed (so weekend/after-hours cases are explainable).
3. No scattered IBKR connection calls remain; all route through ConnectionManager.
4. Market-data snapshot waits are deterministic and do not regress PR #174 behaviour.
5. All mandatory verification commands pass.

