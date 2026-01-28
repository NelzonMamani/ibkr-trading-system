# CODEX_STATISTICAL_INTRADAY_MOMENTUM_ALIGNMENT_AND_FIX.md
**Status:** Authoritative Codex execution document  
**Scope:** Statistical Intraday Momentum (SIMomentum) strategy — align with current system architecture, ensure end‑to‑end operability, and make runtime auditable across all modes.  
**Assumption:** The prior document `CODEX_IMPLEMENTATION_INSTRUCTIONS.md` has been executed and merged, including the new architecture (scanner = measurements, strategy policy = decisions, orchestrator = routing/coordination), and the strategy module exists.

---

## 0) Non‑Negotiables (Do Not Deviate)
1. **No parallel changes.** One PR only: `codex/fix-statistical-intraday-momentum-alignment`.
2. **Do not “silence” failures.** Any failure must be fixed, then the verification commands re‑run.
3. **Strategy must be auditable from console output alone** (what happened, why it happened, what is next).
4. **All modes must start successfully** and the strategy must be observable in the workflow:
   - `SIM`
   - `PAPER`
   - `LIVE_READ_ONLY`
   - `LIVE_MICRO` (guardrails enforced; no unintended order routing)
5. **No changes to Ross strategy requirements** unless needed to preserve shared architecture contracts.

---

## 1) Current Symptoms (Observed)
From the provided logs, we have these concrete issues:

### A. Strategy is disabled by config
Boot output:
- `Strategy 'StatisticalIntradayMomentum' DISABLED via config (STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED=False); skipping.`  
This explains “I haven't seen trades” / “no strategy activity”.

### B. LIVE_READ_ONLY scanner fails with IBKR error 162 and snapshot timeouts
Log excerpt:
- `Error 162, reqId 3: Historical Market Data Service error message: API scanner subscription cancelled`
- `DROP_SNAPSHOT_TIMEOUT`

This is likely from **calling historical endpoints inside the scanner gates** (or calling `reqHistoricalData` / too many requests / wrong contract qualification) while also trying to snapshot many symbols quickly. In LIVE_READ_ONLY you’re also connecting to IBKR; you must ensure **snapshot flow is purely market data snapshot**, not historical, and **rate-limit** if you do any historical calls (preferably: do none at scanner stage).

### C. Session gating mismatch
Even when detected session is `AFTER` / phase `CLOSED`, the scanner prints `SESSION=REG` and the policy allowlist includes `"session_allowlist": ["REG"]`.  
This can cause:
- Strategy blocked unexpectedly
- Scanner using “REG” gates during closed session
- Confusing audit trail

### D. Scanner returns valid Watchlist-K but strategy does not proceed to signals/trades
In SIM mode we see scanner stages and watchlist selection, but we do not see a clear “Strategy evaluation → signals → orders (or explicitly none)”.

---

## 2) Target Behaviour (Definition of Done)
### 2.1 Startup & registration
- Strategy must register when enabled:
  - `STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED=True` should always create an active strategy instance when selected.
- When selected via CLI `--strategy statistical_intraday_momentum`, the boot log must show:
  - Strategy instantiated
  - Policy loaded (version, commit hash if available)
  - Strategy lifecycle hooks reachable (evaluate cycle)

### 2.2 Scanner integration
- Orchestrator requests candidates from scanner using **policy-defined universe**.
- Scanner returns:
  - `raw_candidates` (N up to cap)
  - `after_gates` (symbols with drop reasons)
  - `watchlist_k` (K)
  - optional `focus_m` (M)
  - plus **measurements only** (no decision logic beyond gates and data quality).
- **Scanner must not call IBKR historical data** during gating/enrichment in LIVE_READ_ONLY/LIVE_MICRO/LIVE unless explicitly configured and rate-limited.

### 2.3 Strategy evaluation
- Strategy must print (auditable):
  - inputs received (watchlist/focus + key measurements)
  - gating decisions (per symbol reasons)
  - signals produced (if any)
  - if no signals: explicit reason summary

### 2.4 Execution and mode safety
- SIM/PAPER: execution engine can simulate/route based on mode.
- LIVE_READ_ONLY: no execution; but strategy still evaluates and prints signals.
- LIVE_MICRO: orders allowed only with guardrails; if not acked, hard block and print.

---

## 3) Implementation Plan (What Codex Must Do)

### 3.1 Locate the strategy module and its contracts
Search the repo for:
- `strategies/statistical_intraday_momentum/`
- `StatisticalIntradayMomentum` class
- `strategy_policy.py` (or policy file)
- registry wiring (factory/strategy_runner/orchestrator)

MANDATORY: produce an “inventory report” in PR description:
- exact file paths
- class names
- entrypoints called by orchestrator/runner
- config flags used (with defaults and sources)

### 3.2 Fix strategy enablement and config resolution
Ensure:
- `STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED` is read from env/config registry properly.
- The strategy is **enabled by default only in SIM** is acceptable, but MUST be explicit:
  - If you choose “disabled by default”, then console must instruct user:  
    `Set STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED=True to enable`
- `--strategy statistical_intraday_momentum` should not silently skip strategy if enabled flag is true.

Add an explicit boot line:
- `[BOOT][STRATEGY] StatisticalIntradayMomentum enabled=<bool> selected=<bool> reason=<...>`

### 3.3 Align session handling end-to-end
Define a single canonical session enum or string mapping used everywhere:
- orchestrator session detection
- policy session allowlist
- scanner `SESSION=...` prints

Rules:
- If market is `AFTER`/`CLOSED`, strategy may still evaluate in SIM and LIVE_READ_ONLY (scan-only),
  but **policy session_allowlist must be honoured** and the audit should clearly say when evaluation is skipped due to session.

If policy says `["REG"]` and we are `CLOSED`, then:
- scanner may still collect watchlist (optional), but strategy evaluation must print:
  - `SKIP_EVALUATION reason=SESSION_NOT_ALLOWED session=CLOSED allowlist=['REG']`

No silent skips.

### 3.4 Remove historical calls from scanner gates (or hard-isolate them)
This is the most likely cause of IBKR error 162 during scanner gates.

Codex must:
1. Search for any IBKR historical requests triggered by scanner gating/enrich:
   - `reqHistoricalData`
   - `historical` in provider
   - any function named `get_history`, `fetch_bars`, etc. called from scanner.
2. If found, implement **one** of the following (choose the safest):
   - **Preferred:** move historical data requests to strategy evaluation stage (post-watchlist) and only for Focus-M symbols.
   - **Alternative:** guard historical calls with:
     - `if run_mode in (SIM, PAPER) or HISTORICAL_ENRICH_ENABLED=True`
     - strict rate limit
     - per-symbol timeout
     - fail-soft to “missing enrichment” without dropping entire scan.

In LIVE_READ_ONLY and LIVE_MICRO:
- default: **no historical calls during scanner**.

### 3.5 Fix snapshot timeouts deterministically
Observed `DROP_SNAPSHOT_TIMEOUT` indicates we did not receive required tick fields in time.

Codex must ensure that for each symbol snapshot we:
- qualify contract (async or cached)
- request snapshot
- wait until we have:
  - last OR close (fallback rules)
  - bid/ask if required by policy
  - volume if required
- enforce `IBKR_SNAPSHOT_TIMEOUT_SECONDS` per symbol
- if missing, drop with explicit missing-fields list:
  - `DROP_SNAPSHOT_TIMEOUT missing=['last','bid','ask']`

Additionally:
- In LIVE_READ_ONLY, set market data type intentionally (DELAYED vs LIVE).
- Ensure we are not exceeding IBKR pacing by blasting 50 snapshot requests at once:
  - Use a bounded concurrency (e.g., 5–10 at a time).
  - Or sequential with small delay if needed.

### 3.6 Make the strategy produce observable outputs
Right now we see scan + watchlist, but not strategy evaluation.

Add these console sections (single-line prefixes for greppable logs):
- `[SIMOM][CYCLE] start tick=... mode=... session=...`
- `[SIMOM][INPUT] watchlist_k=[...] focus_m=[...]`
- `[SIMOM][EVAL] symbol=... features={...} decision=... reasons=[...]`
- `[SIMOM][SIGNAL] symbol=... side=... type=... confidence=...`
- `[SIMOM][ORDERS] submitted=<n> blocked=<n> reason=<...>`
- `[SIMOM][SUMMARY] considered=<n> signals=<n> orders=<n> skipped=<n>`

In LIVE_READ_ONLY:
- `[SIMOM][ORDERS] HARD_DISABLED mode=LIVE_READ_ONLY signals=<n>`

### 3.7 Strategy should be deterministic in SIM mode (so we can test quickly)
If the system is in SIM mode with MOCK scanner data, we need a deterministic scenario where the strategy produces either:
- at least one signal (preferred), or
- a deterministic “no signal” explanation.

Implement a minimal deterministic test harness:
- a fixed mock watchlist with measurements that trigger a known signal condition.

This does **not** mean “fake trades”; it means predictable evaluation.

---

## 4) Mandatory Verification Commands (Codex Must Run and Paste Output)
Run from repo root on Windows PowerShell (matches user environment).  
If any fails, fix and rerun until passing.

### 4.1 Static checks
```powershell
python -m compileall -q src
pytest -q
```

### 4.2 SIM mode (strategy enabled)
```powershell
$env:STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED="True"
python -m src.main --mode SIM --cycles 2 --strategy statistical_intraday_momentum
```
Expected:
- Strategy registered and active
- Scanner outputs watchlist
- Strategy evaluation logs appear
- Either signals or a clear no-signal summary

### 4.3 SIM mode (strategy disabled)
```powershell
Remove-Item Env:STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED -ErrorAction SilentlyContinue
python -m src.main --mode SIM --cycles 1 --strategy statistical_intraday_momentum
```
Expected:
- Explicit boot message that strategy is disabled and how to enable it

### 4.4 LIVE_READ_ONLY scan-only (no crash)
```powershell
$env:IBKR_HOST="127.0.0.1"
$env:IBKR_PORT="7496"
$env:IBKR_CLIENT_ID="91"
$env:STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED="True"
python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy statistical_intraday_momentum
```
Expected:
- Connects to IBKR
- Scanner returns watchlist without error 162
- Strategy evaluates
- Orders hard disabled

### 4.5 PAPER mode (no unintended routing changes)
```powershell
$env:IBKR_CLIENT_ID="92"
$env:STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED="True"
python -m src.main --mode PAPER --cycles 1 --strategy statistical_intraday_momentum
```
Expected:
- Uses paper broker adapter (or sim broker if that is your architecture)
- No hard failures

### 4.6 LIVE_MICRO guardrails (must block unless acked)
```powershell
$env:IBKR_CLIENT_ID="93"
Remove-Item Env:LIVE_MICRO_ACK -ErrorAction SilentlyContinue
$env:STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED="True"
python -m src.main --mode LIVE_MICRO --cycles 1 --strategy statistical_intraday_momentum
```
Expected:
- Hard block order submission with clear message (unless your system requires ack via env)

Then with ack:
```powershell
$env:LIVE_MICRO_ACK="True"
python -m src.main --mode LIVE_MICRO --cycles 1 --strategy statistical_intraday_momentum
```
Expected:
- If any orders would be submitted, they must be capped to 1 share and within max trades/day/loss.

---

## 5) PR Acceptance Checklist (Codex Must Satisfy)
- [ ] Strategy enable flag is honoured and auditable.
- [ ] Strategy evaluation logs appear in SIM and LIVE_READ_ONLY.
- [ ] LIVE_READ_ONLY run does **not** trigger IBKR historical error 162 during scanner stage.
- [ ] Snapshot timeout drops include missing-field details.
- [ ] Session handling is consistent and skips are explicit.
- [ ] `pytest -q` passes.
- [ ] `python -m compileall -q src` passes.
- [ ] All mandatory verification commands are run and pasted into `PR_VERIFICATION_REPORT.md`.

---

## 6) Implementation Notes (Strong Guidance)
### 6.1 Where to put the “audit prints”
Prefer:
- strategy module logger / print wrapper
- do not sprinkle prints in unrelated components
- keep prefixes consistent (`[SIMOM]`)

### 6.2 Avoid broad refactors
We are aligning strategy with architecture; do not rename core engine classes, do not restructure unrelated strategies.

### 6.3 Treat IBKR pacing as real
Even on delayed data, IBKR pacing limits exist. If you must snapshot many symbols:
- concurrency limit
- caching of contract qualification
- per-cycle cap enforced

---

## 7) Deliverables
Codex must add/update these files:
1. `PR_VERIFICATION_REPORT.md` (updated with outputs)
2. If missing: `strategies/statistical_intraday_momentum/README.md` explaining enable flag, modes, expected console markers.
3. Any required code changes to:
   - strategy registration
   - orchestrator integration
   - scanner gating/enrichment isolation
   - snapshot wait correctness
   - mode/session alignment

No other documents are required.

---

## 8) Stop Condition
Codex must STOP after:
- all verification commands pass
- PR verification report is complete
- outputs demonstrate the strategy lifecycle clearly in console

Do not continue to add features beyond alignment and operability.
