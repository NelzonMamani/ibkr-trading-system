# 03_SCANNER_SESSION_CONTRACT.md
TITLE: Scanner Correction — Session-Aware Facts, Monday Prep, Strategy-Compatible Output
DATE: 2026-01-31

## 1. Goal
Make scanner output **session-qualified facts** that are trustworthy in CLOSED/PRE/RTH/AH, including weekends/holidays, so strategies can reliably build watchlists and prepare for Monday.

## 2. Non-negotiables
- Scanner does **not** decide trades or strategy eligibility.
- Scanner output must be **explicitly session-qualified**.
- Scanner must support CLOSED-mode preparation for next tradable session.
- Output must be fast; heavy enrichment must be avoided on hot path.

## 3. Deliverables (ordered)

### 3.a Session derivation (authoritative)
Implement a single source of truth for session detection used everywhere:
- Inputs: exchange calendar + current timestamp
- Outputs:
  - `session_label` in {CLOSED, PRE, RTH, AH}
  - `next_session_label` (for prep)
  - `session_start_ts`, `session_end_ts`
  - `is_weekend`, `is_holiday`
  - `last_rth_close_ts`

Must treat weekends/holidays as CLOSED with a next tradable session (typically Monday PRE).

### 3.b Reference price contract (authoritative)
Scanner must compute / fetch and **label** reference prices:
- `reference_price_type` in {
    "RTH_CLOSE",
    "PRIOR_RTH_CLOSE",
    "PRE_MARKET_OPEN",
    "LAST_TRADE",
    "LAST_AVAILABLE"
  }
- `reference_price` numeric
- `reference_timestamp`

Percent change must be computed relative to a labeled reference:
- In CLOSED: reference is **last RTH close** (e.g., Friday close)
- In PRE: reference is last RTH close
- In RTH: reference is prior close (same as last RTH close)
- In AH: reference is same-day RTH close

If reference cannot be determined, scanner must set:
- `pct_change = None`
- `data_quality_flags += ["MISSING_REFERENCE_PRICE"]`
…and must not silently fabricate.

### 3.c RVOL contract (session-qualified)
RVOL must be explicitly defined and session-aware.
At minimum for Ross selection:
- In PRE: “premarket relative volume” must compare PRE volume to a baseline (e.g., average PRE volume or a proxy).
- If baseline is not available, set RVOL to None and set data-quality flag.
Do not show RVOL numbers that are not interpretable.

### 3.d Data quality flags (first-class)
Scanner output must include:
- `data_quality_flags: list[str]`
Examples:
- NO_MARKET_DATA
- STALE_SNAPSHOT
- OTC_OR_INELIGIBLE
- HALTED
- SSR
- WIDE_SPREAD
- LOW_LIQUIDITY
- MISSING_FLOAT
- MISSING_NEWS
- MISSING_REFERENCE_PRICE
These flags are facts; strategy policy decides what to do with them.

### 3.e Output schema: strategy-compatible facts
Scanner must output a uniform “facts payload” per symbol including at least:
- symbol
- last_price
- bid/ask/spread (if available)
- session_label, reference_price_type, reference_price, pct_change
- volumes (session volume and/or cumulative)
- rvol (optional; None allowed)
- float_shares (optional; None allowed) + float_source
- news/catalyst presence indicator (optional)
- halts/SSR flags (if available)
- timestamps (snapshot ts)

### 3.f Monday prep flow (CLOSED mode)
When session_label=CLOSED:
- Scanner must still run and produce “prep-ready” output:
  - top gainers list based on last available data
  - reference is last RTH close (Friday close)
  - output is tagged for next tradable session (Monday PRE)
- The system must persist:
  - candidate list
  - key reference prices
  - data-quality flags
so Monday morning starts from prepared context.

### 3.g “No heavy enrichment on hot path”
The scanner must remain fast:
- Avoid long web scraping during scan.
- Float/news may use cached providers; if missing, mark as missing.
- Strategy policy may optionally request enrichment for **focus** list, not for raw scan.

## 4. Hard rule: scanner is not strategy-aware
Scanner MUST NOT implement:
- Ross 5 pillars gating
- pattern detection
- trade signals

These live in `strategies/<strategy>/strategy_policy.py`.

## 5. Acceptance tests (conceptual)
- On a weekend (CLOSED), scanner produces output with `session_label=CLOSED` and `reference_price_type=RTH_CLOSE`.
- On Monday PRE, scanner uses Friday close reference.
- Output includes explicit reference timestamps and data_quality_flags.
- Strategies receive sufficient facts to build watchlists without guessing.

END
