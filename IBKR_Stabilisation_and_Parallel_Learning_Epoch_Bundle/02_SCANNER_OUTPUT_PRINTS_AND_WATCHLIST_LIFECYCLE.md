# 02 — SCANNER OUTPUT PRINTS AND WATCHLIST LIFECYCLE (TopN→WatchlistK→FocusM)

## Objective
Make the scanner stage **observable and verifiable** by printing:
1) The **Watchlist K (15)** with the **filter variables** (“Ross pillars + practical gates”).
2) The **Focus M (3–5)** with the same fields **plus ranking rationale** and news/catalyst summary.

This must be done without rendering a table; **print one symbol per line** with attached variables.

## Scope constraints
- Do **not** implement new trading logic.
- Do **not** change the “scanner is mechanical, policy is in strategy” architecture.
- This work is **printing + data plumbing + watchlist persistence**, not strategy entry rules.

## Definitions
- **TopN (N=50)**: raw “top gainers” set from IBKR (or symbol list fallback).
- **Watchlist K (K=15)**: survivors after hard gates + ranking.
- **Focus M (M=3–5)**: subset of Watchlist K used for intensive evaluation.

## Required parameters passed to scanner (source=STRATEGY policy)
The scanner should receive (at minimum) the following from the Ross strategy policy:
- `price_min`, `price_max`
- `gap_min_pct` (and optional max if present)
- `rvol_min`
- `float_max_millions`
- `min_volume`
- `min_premarket_volume`
- `require_catalyst`
- `allow_halts`
- `allow_ssr`
- `data_quality_require_price`
- `data_quality_require_bid_ask`
- `watchlist_limit_k`
- `focus_limit_m`
- `top_gainers_n`
- `max_symbols_per_cycle`
- `ranking_intent` (string for explainability)

The scanner may use optional **context gates** if already in Ross policy:
- liquidity min $ volume
- spread max pct
- max halt/SSR rules if present

## Data model (must exist and be returned by scanner)
Introduce or confirm a stable dataclass (names can vary, but must be explicit):
### CandidateMetrics (one per symbol)
Fields (minimum):
- symbol: str
- last_price: float|None
- prev_close: float|None
- gap_pct: float|None
- pct_change: float|None  (session change, if computed)
- rvol: float|None
- float_shares: int|None
- float_millions: float|None
- volume: int|None
- premarket_volume: int|None
- dollar_volume: float|None
- spread_pct: float|None
- halted: bool|None
- ssr: bool|None
- catalyst_present: bool|None
- catalyst_summary: str|None  (short, 1-line)
- data_quality_ok: bool
- drop_reasons: list[str]  (empty if survivor)
- rank_score: float|None
- rank_components: dict[str, float]|None (optional but recommended)
- timestamp_utc: str (ISO)

### ScannerResult
Must include:
- top_n_symbols: list[str]
- candidates: list[CandidateMetrics] (all evaluated)
- watchlist_k: list[CandidateMetrics] (K survivors, ordered)
- focus_m: list[CandidateMetrics] (M, ordered)
- drops_by_reason: dict[str, int]
- new_symbols: list[str]
- continuing_symbols: list[str]
- dropped_symbols: list[str]

## Printing requirements
### A) Watchlist K print (15 lines)
One line per symbol, fields in this exact spirit (format can vary, but must be stable):
- `SYMBOL price=$X gap=Y% chg=Y% rvol=Z float=Xm vol=V pm=PM spread=S% catalyst=YES/NO halted=Y/N ssr=Y/N dq=OK/BAD score=...`

Rules:
- Missing values print as `NA`
- Float prints in **M** when available, else shares
- Keep catalyst summary truncated (e.g., 80 chars)
- If the symbol barely passes, still print (this is the whole point: visibility)

### B) Focus M print (3–5 lines)
Same as Watchlist K plus:
- rank_components (if you have them) or a 1-line “why”
- explicit “passes/policy thresholds” recap:
  - `price_range_ok`, `gap_ok`, `rvol_ok`, `float_ok`, `volume_ok`, `pm_volume_ok`, `catalyst_ok`, etc.

### C) Drop summary print
Print:
- total TopN
- total evaluated
- total dropped
- top drop reasons with counts

## Watchlist lifecycle (avoid garbage; keep the latest)
### A) Persisted watchlist concept
Maintain a **single “latest watchlist” per strategy** in the DB and optionally a daily history (bounded).
Rules:
1. Generate/refresh watchlist during **PRE** session.
2. During REG/AFTER:
   - update only if TopN materially changes (see change detection below) OR if no watchlist exists.
3. At end of day:
   - keep the **last watchlist** as “carry-over”
   - delete older intraday watchlists for that day beyond retention.

### B) Change detection (deterministic)
Consider watchlist “changed” if:
- the set of Watchlist K symbols changes, OR
- the order changes materially (e.g., Kendall tau below a threshold) OR
- the Focus M changes.

For simplicity: start with **set change** only.

### C) Storage schema (minimal)
If you already store events + TradeRecord, you can store watchlist as:
- a table `watchlists` with:
  - id, strategy_name, asof_date (NY date), session_phase, created_at_utc
  - symbols_json (ordered list)
  - focus_json
  - hash (for change detection)
  - metrics_json (optional snapshot for later learning)

If DB migrations exist, use the same pattern as the rest of the repo.

## Execution mode constraints
- In LIVE_MICRO, these prints must occur but must not spam:
  - print Watchlist K only when it changes, or at least once per session phase boundary.
- Add config `WATCHLIST_PRINT_EVERY_N_CYCLES` (default 20) if needed.

## Acceptance criteria
1. A single run:
   - `python -m src.main --mode LIVE_MICRO --cycles 1`
   prints:
   - Watchlist K lines (even if fewer than 15 due to limited `SCANNER_SYMBOLS`)
   - Focus M lines
   - Drop summary and policy echo (already present)
2. In subsequent cycles with unchanged inputs, it does not re-create/re-print watchlist every cycle.
3. Unit tests cover:
   - formatting stable enough to assert key tokens
   - change detection works
   - ScannerResult includes CandidateMetrics objects (not bare strings)

## Mandatory Verification Commands (must run and report)
Run the commands in `99_MANDATORY_VERIFICATION_COMMANDS.md` and include:
- a pasted example of the Watchlist K and Focus M printouts (redact nothing; this is internal).

END
