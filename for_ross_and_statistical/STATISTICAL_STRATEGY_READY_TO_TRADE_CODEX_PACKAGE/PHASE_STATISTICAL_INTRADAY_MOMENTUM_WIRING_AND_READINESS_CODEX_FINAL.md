# PHASE_STATISTICAL_INTRADAY_MOMENTUM_WIRING_AND_READINESS_CODEX_FINAL
Last updated (UTC): 2026-01-25 22:36:06Z

## Purpose
This document is the authoritative, exhaustive instruction set for Codex to:
1) Make the **Statistical Intraday Momentum** strategy *selectable* and *reachable* through the system interface (CLI → config → orchestrator → strategy).
2) Ensure **pre-session preparation artefacts** exist, are persisted, are loaded, and are verifiably valid.
3) Add **mandatory verification commands** that prove correctness across **all existing run modes** without introducing new modes.
4) Iterate fixes until **all verification commands pass** (fail-closed safety; never trade if readiness fails).

This work is explicitly **integration + readiness + observability**, not new strategy invention.

---

## Evidence-bound constraints (do not violate)
### Existing run modes (MUST NOT CHANGE)
The system itself currently advertises these run modes via `python -m src.main --help`:

- SIM
- READONLY
- PAPER
- LIVE_1SHARE
- LIVE
- LIVE_READ_ONLY
- LIVE_MICRO

**Codex MUST NOT** add, remove, rename, alias, or reinterpret any mode. Any change to these enums is a breaking change and forbidden.

### Existing strategy choice currently restricted (MUST FIX)
Current CLI restricts `--strategy` choices to `{ross_momentum}` only. This must be extended to include the statistical strategy.

---

## Strategy intent (Statistical Intraday Momentum)
The statistical strategy does **not** “discover” symbols itself. It consumes a broad, mechanical opportunity surface produced by the scanner/orchestrator pipeline.

### Required pre-session artefacts (MUST EXIST)
A1) **Baseline Liquidity & Tradability Universe** (daily/session artefact; mechanical eligibility list)  
A2) **Historical Intraday Distribution Store** (time-of-day / regime conditioned statistics)  
A3) **Session Readiness State** (PRE / REGULAR / AFTER / CLOSED + eligibility flags)

These artefacts must be:
- persisted (SQLite or files under `data/`)
- versioned/dated (NY session date)
- loaded at startup (all modes)
- reused (not recomputed each cycle)
- observable in logs
- fail-closed if missing/invalid

Explicitly NOT required for this strategy:
- float cache
- news/catalyst cache
- Ross pattern suite cache

---

# PART A — Wiring: make the statistical strategy reachable

## A.1 Update CLI (`src/main.py`) to accept the statistical strategy
1) Find the argparse definition for `--strategy`.
2) Extend `choices` to include:
   - `statistical_intraday_momentum`

Canonical key must be **lower_snake_case**. Do not use uppercase names.

### Acceptance criteria
Running must not error:
- `python -m src.main --strategy statistical_intraday_momentum --mode PAPER --cycles 1`

If it errors with “invalid choice”, wiring is not complete.

## A.2 Register the strategy in StrategyRegistry
Locate registry (commonly `src/core/strategy_registry.py` or similar). Ensure:
- Key: `statistical_intraday_momentum`
- Value: Strategy class implementing the strategy interface used by StrategyRunner.

## A.3 Orchestrator routing
When strategy key = `statistical_intraday_momentum`:
- Orchestrator loads **statistical policy** (not Ross policy).
- Ross Momentum pattern suite must **not** be instantiated as the active pattern engine for this strategy.
- StrategyRunner must either:
  - run only the selected strategy, or
  - if multi-strategy is supported, it must be explicitly opt-in and clearly logged.
- No silent fallback to Ross.

### Required log lines (or equivalent)
At startup or first cycle, logs must clearly show:
- `[BOOT] Strategy 'StatisticalIntradayMomentum' ENABLED`
- No lines of the form: `loaded strategy=ross_momentum` when statistical strategy is selected.

---

# PART B — Preparation artefacts: materialise, persist, load, reuse

## B.1 Storage plan (authoritative and minimal-risk)
Preferred: use existing SQLite `data/ibkr_system.db` via StorageEngine.  
Alternative: file cache under `data/cache/`.

For each artefact (A1/A2/A3), persist metadata:
- `artefact_name`
- `session_date` (NY market date)
- `created_at_utc`
- `version` or `hash`
- `count` (when applicable)
- `source` (how built)
- `valid_until` or an explicit `is_valid_for_session` method

## B.2 Artefact A1 — Baseline Liquidity & Tradability Universe (MANDATORY)
Implement a builder that produces a baseline universe of symbols that are:
- liquid enough for intraday inference
- spread/turnover sane
- data-available

Key properties:
- computed **once per NY session date** (or reused if exists)
- does not depend on Ross pillars (gap/rvol/float/news)
- provides a symbol list (count > 0) and a small sample for logging

Examples of mechanical gates (tunable):
- average daily dollar volume above threshold
- average daily share volume above threshold
- last price above absolute minimum (avoid pennies unless explicitly supported)
- spread percentage below threshold

### REQUIRED runtime behaviour
On startup (all modes), log:
- whether the baseline universe was loaded from cache or built fresh
- `session_date`, `created_at`, `count`, and a sample list of tickers

## B.3 Artefact A2 — Historical Intraday Distribution Store (MANDATORY)
This must exist for the statistical strategy to be live-ready.  
If not yet computed, the correct behaviour is:
- mark readiness as FAIL
- disable trading (fail-closed)
- print explicit message: “Missing statistical distributions store; trading blocked”

Do not silently substitute Ross metrics.

## B.4 Artefact A3 — Session Readiness State (MANDATORY)
Ensure the system computes and logs:
- session phase PRE/REGULAR/AFTER/CLOSED
- whether the statistical strategy is permitted to evaluate/trade in this phase
- (optional) symbol eligibility tags for current phase

---

# PART C — Mandatory readiness framework (must run in all modes)

## C.1 Implement a readiness report
Add `src/core/readiness.py` (or nearest appropriate module) that exposes:
- `run_readiness_check(cfg) -> ReadinessReport`
- `ReadinessReport.to_text()` for deterministic logs
- `ReadinessReport.is_pass` boolean
- explicit `fail_reasons: list[str]`

The readiness check must validate:
- strategy selection is recognized and active
- A1 exists + valid + loaded + count > 0
- A2 exists + valid + versioned (or FAIL with explicit reason)
- A3 exists + computed

## C.2 Fail-closed enforcement (all live-capable modes)
If readiness FAIL:
- In LIVE/LIVE_1SHARE/LIVE_MICRO: **no order submission**. ExecutionEngine must be gated or Orchestrator must set `trade_enabled=False`.
- In PAPER: allow pipeline to run but default to fail-closed unless explicitly overridden.
- In READONLY/LIVE_READ_ONLY/SIM: never trade anyway, but must still report readiness.

## C.3 Add a CLI flag: `--readiness-check`
When present:
- run readiness check
- print report
- exit 0 if PASS else exit nonzero
- do not enter continuous loop

---

# PART D — Mandatory verification commands (Codex must add + keep green)

## D.1 Baseline: CLI mode list proof
Command:
- `python -m src.main --help`

Expected:
- Mode list remains unchanged (no drift)
- Strategy list includes `statistical_intraday_momentum`

## D.2 Readiness check across ALL modes (must PASS)
For each mode in:
- SIM
- READONLY
- PAPER
- LIVE_READ_ONLY
- LIVE_1SHARE
- LIVE_MICRO
- LIVE

Command pattern:
- `python -m src.main --strategy statistical_intraday_momentum --mode <MODE> --readiness-check`

Expected:
- prints readiness report
- exit code 0 (PASS) when A1/A2/A3 are present/valid
- if A2 is missing, readiness must FAIL with explicit reason (no silent fallback) until Codex provides the store and makes it PASS.

## D.3 Strategy non-fallback proof
Run once:
- `python -m src.main --strategy statistical_intraday_momentum --mode READONLY --cycles 1`

Expected log invariants:
- no Ross policy loaded
- no “ross_momentum” selected
- StrategyRunner includes the statistical strategy as active

## D.4 Prepared symbol list proof
In readiness report, must include:
- A1 universe count and sample symbols
- “Candidate intent universe” count (if scanner produces it)
- separation between:
  - baseline universe (A1)
  - per-cycle candidates
  - strategy-selected actionable symbols (if any)

---

# PART E — Fix-until-pass loop (MANDATORY)
Codex must:
1) Implement Parts A–D.
2) Run the verification commands.
3) If any command fails:
   - diagnose root cause
   - apply targeted fix
   - rerun until all commands pass
4) Provide a verification report listing each command + PASS/FAIL.

No partial delivery is acceptable.

---

# PART F — Deliverables to commit
Codex must commit:
1) wiring changes (CLI/registry/orchestrator)
2) readiness module + fail-closed gating
3) artefact builders/loaders for A1/A2/A3
4) `--readiness-check` CLI flag
5) documentation updates (how to verify)

Additionally, commit the PowerShell script `tools/VERIFY_STATISTICAL_ALL_MODES.ps1` (from this package).

---

## STOP CONDITION
Complete only when:
- statistical strategy is selectable
- readiness PASS in all modes
- baseline universe is built/loaded and logged
- no Ross fallback occurs when statistical selected
- verification scripts exit 0
