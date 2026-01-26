# PHASE_RM_FINAL_INSTRUCTIONS_v1_0
**File:** PHASE_RM_FINAL_INSTRUCTIONS_v1_0.md  
**Version:** v1.0 (Final Instruction Set)  
**Status:** Authoritative — copy/paste into Codex as a single block, and require Codex to follow it exactly.  
**Created:** 2026-01-25

---

## 0) Objective (Definition of Done)
“Done” means the system can run end-to-end in LIVE_MICRO/SIM with **Ross Momentum** behaving deterministically and verifiably:

1. **Scanner → Watchlist K → Focus M** works under **PRE / RTH / AH / WEEKEND / HOLIDAY** modes without percent-change/RVOL ambiguity.
2. **Stock selection** uses the canonical Ross 5 pillars + tradability gates **from policy**, not ad-hoc scanner code.
3. **All Ross setup families** listed in `SETUP_FAMILIES_AND_PATTERNS.md` are implemented as real detectors, wired into evaluation and intent generation.
4. There is a **verification harness** that prevents “partial implementations” from reappearing:
   - Pattern coverage report **fails** if any required pattern is missing, unregistered, or untested.
   - Session audit prints active mode and reference baselines used (prices/volumes).
   - Float audit prints raw float + formatted K/M/B + source + cache behavior.
5. All checks below pass: compile, tests, coverage, audits, and a controlled dry-run.

---

## 1) Non‑negotiable design constraints
- **Single source of truth for stock selection:** `strategies/ross_momentum/strategy_policy.py::StockSelectionSpec`.
- Scanner must be **mechanical and strategy-agnostic**; it may collect raw facts, but not enforce Ross logic beyond hard tradability gates required by system safety.
- Strategy policy & strategy context schema remain the canonical contract:
  - `strategies/ross_momentum/strategy_policy.py`
  - `strategies/ross_momentum/strategy_context_schema.py`
- Do not introduce silent heuristics; if a new rule is added, it must be:
  1) in policy, 2) surfaced in telemetry, 3) covered by tests.

---

## 2) Implementation tasks (Codex must complete all)
### 2.1 Stock selection consolidation (policy becomes authoritative)
**Goal:** All Ross stock-selection logic lives in Ross policy layer and is applied consistently in all session modes.

**Required actions**
1. Locate and remove/disable any duplicated stock-selection logic currently living in:
   - scanner modules
   - orchestrator pass-through logic
   - strategy runner ad-hoc filters
2. Ensure orchestrator passes `StockSelectionSpec` into the scan/filter pipeline.
3. Ensure the selection output includes:
   - Watchlist K (<= `watchlist_limit_k`)
   - Focus M (<= `focus_limit_m`)
4. Ensure ranking is stable and explicit:
   - Primary sort: percent change (mode-correct baseline)
   - Secondary: RVOL
   - Tertiary: float ascending
   - (Any tie-breakers must be documented and tested.)

**Acceptance**
- A single, unit-testable function exists: `apply_ross_stock_selection(policy, candidates, session_context)`.

---

### 2.2 Session/mode correctness (PRE/RTH/AH/WEEKEND/HOLIDAY)
**Goal:** Percent change and RVOL reference baselines are always correct and explainable.

**Required actions**
1. Add/confirm a canonical `SessionClassifier`:
   - Inputs: now_utc, now_ny, now_uk, market calendar
   - Output: one of `{WEEKEND, HOLIDAY, PRE, RTH, AH, CLOSED}` plus a `RossTradingMode` mapping.
2. Implement **explicit baseline rules**:

**Percent change baselines**
- **RTH %change:** `last_price` vs **prior close** (yesterday close)
- **Premarket %change:** `premarket_last` vs **prior close**
- **After-hours %change:** `after_hours_last` vs **RTH close**
- **Weekend/Holiday %change:** compare **last trading day close** vs **previous trading day close**
  - Example: Sunday → Fri close vs Thu close (with holiday-adjusted last trading day logic)

**Volume/RVOL baselines**
- RVOL must be computed using two diagnostic columns:
  - `RVOL_20D`: today volume vs avg volume of prior 20 sessions
  - `RVOL_1D`: today volume vs prior 1 session volume (yesterday)
- Both columns are for troubleshooting and transparency; the strategy can choose which one drives gates.

3. Add a `session_audit` CLI tool (see §4).

**Acceptance**
- `session_audit` prints the mode and the actual baseline timestamps/prices/volumes used.
- No “N/A” due to ambiguity; only “N/A” when data truly missing, with reason.

---

### 2.3 Float acquisition and caching (Yahoo/Finviz/Nasdaq, optional IB fundamentals)
**Goal:** Float is always available when possible; missing float is explicit and debuggable.

**Required actions**
1. Create `FloatProvider` with ordered fallbacks:
   1) Yahoo Finance
   2) Finviz
   3) Nasdaq (if feasible and stable)
   4) IB fundamentals (if available in your subscription)
2. Store:
   - raw float integer
   - formatted string (K/M/B)
   - source
   - fetch timestamp
   - cache hit flag
3. Cache semantics:
   - Cache by symbol + trading date
   - Reuse cached float all session (float is static day-to-day for our purposes)

4. Add a `float_audit` CLI tool (see §4).

**Acceptance**
- `float_audit` prints non-N/A float for a representative set of symbols where data exists.
- Cache hit occurs on second run.

---

### 2.4 Pattern completeness: implement all setup families and micro-patterns
**Goal:** No partial pattern implementation. All patterns in `SETUP_FAMILIES_AND_PATTERNS.md` exist as detectors and are test-covered.

**Required patterns (deduped canonical set)**
1. Gap & Go (Opening Drive)
2. Opening Range Breakout (ORB)
3. First Pullback / First Flag
4. Micro Pullback (10s/15s execution; impulse-normalised)
5. Bull Flag / High-Tight Flag
6. Break of Key Level (PMH/PDH/multi-day/whole-half)
7. ABCD continuation/extension
8. Cup & Handle (intraday)
9. Momentum Reclaim (VWAP/EMA reclaim)
10. Flat-Top / Ascending Breakout
11. Red-to-Green / Green-to-Red (contextual; usually confirmation)
12. Half-Dollar / Whole-Dollar Break (distinct name)
13. Pre-market High Break (distinct name)
14. Halt Resume Continuation
15. Parabolic Exhaustion (avoid/exit family; veto / risk-flag, not entry)

**Required actions**
1. Establish a shared pattern detector interface and a Ross registry list that is the *only* list evaluated for Ross.
2. Wire pattern evaluation → summary → trade intents.
3. Ensure micro-pullback uses the mechanical mapping we agreed:
   - Compare each pullback red candle body to impulse body (default max 0.30)
   - Total pullback range to impulse range (default max 0.50)
   - Topping-risk overlays (pause at 0.40 warning; halt at 0.50+ if configured)
   - Entry trigger: break above **last red high**
4. Ensure “avoid patterns” (parabolic exhaustion) create veto flags that suppress intents.

**Acceptance**
- A coverage report exists and fails if any pattern is missing/untested/unregistered.

---

### 2.5 Trade Permission Matrix and risk overlays
**Goal:** No trades when the permission matrix forbids; no silent overrides.

**Required actions**
1. Ensure the Ross Momentum Risk Overlay is invoked before global risk engine decisions.
2. Ensure permission states exist: `{ALLOW, PAUSE, HALT}` and are recorded per symbol per cycle.
3. Ensure topping/reversal logic runs on the correct timeframe per mode:
   - OPEN_FAST: monitor 1m for topping tails while executing on 10s
   - LATE: monitor 5m/1m as configured
4. Ensure “3 losses rule” hard stop is enforced.

**Acceptance**
- Tests cover at least:
  - PAUSE on topping tail threshold
  - HALT on hard reversal threshold
  - HALT on consecutive losses limit

---

## 3) Mandatory verification harness (must be added if missing)
### 3.1 Pattern unit tests (required for every pattern)
Create `tests/test_ross_pattern_<pattern>.py`:
- One positive fixture must trigger
- One negative fixture must not trigger
- Fixtures must be deterministic (hardcoded candles)

### 3.2 Pattern coverage report (hard gate)
Add `python -m src.strategies.ross_momentum.tools.pattern_coverage_report` which:
- enumerates required pattern names (the list in §2.4)
- verifies:
  - detector exists
  - detector registered in Ross registry
  - at least one unit test file exists for it
- exits **1** if any requirement missing

### 3.3 Session audit tool
Add `python -m src.tools.session_audit` which prints:
- now UTC / NY / UK
- detected session state (PRE/RTH/AH/WEEKEND/HOLIDAY/CLOSED)
- baselines used for percent change (with timestamps)
- baselines used for RVOL_20D and RVOL_1D

### 3.4 Float audit tool
Add `python -m src.tools.float_audit --symbols AAPL,MOVE,DRCT,...` which prints:
- symbol, raw float, formatted, source, timestamp, cache hit

---

## 4) Execution checklist (Codex must run and paste outputs)
Codex must run and paste all outputs (no “trust me”):

1. `python -m compileall src`
2. `pytest -q`
3. `python -m src.strategies.ross_momentum.tools.pattern_coverage_report`
4. `python -m src.tools.session_audit`
5. `python -m src.tools.float_audit --symbols <at least 10>`
6. Run a controlled dry-run (SIM) for 1–2 cycles with logging enabled, and paste:
   - Watchlist K and Focus M outputs
   - Permission matrix states
   - At least one pattern evaluation summary line per focus symbol
7. Provide `git diff --stat` and list touched files.

---

## 5) Troubleshooting protocol (if any check fails)
- If percent change is N/A:
  - session_audit must show which baseline is missing (price missing vs baseline missing).
  - Validate IBKR market data type (delayed-frozen vs real-time) and snapshot completion waits.
- If RVOL is extreme:
  - verify float and low-volume environment; confirm day volume and baseline volumes are correct.
- If float is N/A:
  - float_audit must show which provider failed and why (HTTP status, parse failure).
  - Confirm user-agent headers and rate limiting.
- If pattern coverage fails:
  - implement missing detector + tests + registry entry before any other work.

---

## 6) Deliverable artifact update (documentation)
Update or create:
- `ROSS_MOMENTUM_STRATEGY_COMPLETE_SPEC_v1_1_TEACHING_EDITION.md`
  - Must include: stock selection + mode handling + percent-change/RVOL logic + float logic + pattern catalogue + automation mapping + troubleshooting appendix.

This doc must link to the CLI tools and show example outputs.

---

## 7) Stop condition
If any required pattern, audit tool, or coverage check is missing: **STOP** and implement it before proceeding to further refinements.

---

# END OF INSTRUCTIONS
