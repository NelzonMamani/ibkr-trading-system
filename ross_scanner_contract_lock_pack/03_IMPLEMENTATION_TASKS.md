# 03 — Implementation Tasks (Do exactly)

## Task 1 — Find and lock the Ross scanner subscription parameters
- Identify the exact call path: Orchestrator → Scanner runner → Provider (IBKR).
- Ensure the Ross Momentum strategy passes the StockSelectionSpec fields:
  - price_min=1.0
  - price_max=20.0
  - universe.source=IBKR_TOP_GAINERS
  - universe.ibkr_scan_code=TOP_PERC_GAIN
  - locationCode=STK.US.MAJOR
  - top_gainers_n:
    - PREP/CLOSED mode: 150 (default)
    - otherwise: 50 (default)
- Remove any conflicting CONFIG_DEFAULTS that override Ross.
- Add a single log line in orchestrator that prints the resolved Ross scanner definition.

## Task 2 — Eliminate silent MOCK fallback for Ross in live modes
- If `IbkrScannerProvider.connect()` fails, scanner must:
  - Emit a clear warning
  - Return `[]` symbols
  - Continue pipeline to produce a prep report + empty watchlist artifact
- Only allow MOCK when:
  - run mode is SIM/PAPER
  - or an explicit CLI flag / env var selects MOCK provider
- Ensure printed banner includes `provider=IBKR|MOCK` and `fallback_reason=...`.

## Task 3 — Make scanner strategy-aware without branching logic explosion
- Do NOT add per-strategy `if` ladders in scanner internals.
- Implement a generic request object that carries:
  - instrument, locationCode, scanCode, abovePrice, belowPrice, numberOfRows
- Ross simply supplies values through policy.
- Statistical strategy supplies its own values (could be different).

## Task 4 — Enforce single ranking authority
Pick one:
A) **Strategy-owned ranking** (preferred)
- scanner_runner: sorts only for stable printing (optional), but does not decide watchlist
- orchestrator: does not re-rank watchlist candidates
- strategy_policy.select_watchlist: final ranking (reverse=True) and slices K

OR

B) **Scanner-owned ranking**
- scanner_runner produces watchlist_rows already ranked for Ross
- orchestrator MUST NOT re-sort for Ross

Whichever you choose, remove/disable the other sorts for Ross and add a comment marking the authority.

## Task 5 — Align standalone scanner_main with orchestrator behavior
- `python -m src.scanner.scanner_main` should accept a strategy name or policy selection.
- When invoked for Ross, it must use the same subscription and ranking authority as orchestrator.
- Ensure PRE session prints show `abovePrice=1 belowPrice=20` and do not include large-caps unless IBKR scan returns them (it should not).

## Task 6 — Prep mode behavior when market is closed
- In CLOSED (weekend/holiday) session phase:
  - request TopN=150 (when IBKR available) using Ross subscription
  - compute gates and persist watchlist artifact
  - if IBKR unavailable, persist empty artifact + diagnostics

## Task 7 — Tests
- Update/add tests to cover:
  - Ross scanner request contains correct subscription params.
  - Live modes do not inject MOCK symbols on IBKR failure.
  - Ranking authority is single and deterministic.
  - Watchlist artifact is written even when empty.

Do not weaken tests. Add new ones if required.
