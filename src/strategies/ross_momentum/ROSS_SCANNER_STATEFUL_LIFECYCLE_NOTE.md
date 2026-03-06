# Ross Scanner Stateful Lifecycle Note

## Daily list model
Ross scanner now maintains explicit daily lists for:
- `TOP_UNIVERSE` (broad tracked symbols/ranks)
- `WATCHLIST_K` (symbols passing stock-selection)
- `FOCUS_M` (active setup monitoring list)
- `REJECTED_TRACKED` (rejections cached with reason/staleness)

Daily state resets explicitly at trading-day/session boundaries and is logged.

## Delta update model
Each scan cycle computes universe deltas (`new`, `exited`, `unchanged`, `escalated`) and avoids unnecessary repeat evaluation, especially for bottom-edge oscillators. Symbols are escalated for material rank moves and stale cached outcomes.

## Session-aware metric definitions
- Percent change is computed via deterministic session references with provenance (`reference_label`, `pct_source`).
- Gap is carried as prep/open contextual metadata and logged with source/reference.
- RVOL is session-aware with explicit baseline/method provenance.

## Cache/reuse policy
- Float cache is reused per-day with hit/lookup logging and daily invalidation.
- News enrichment cache is reused by signature and emits `news_changed` diagnostics.
- Rejection decisions are tracked and reused until stale/materially changed.
- Prep outputs and day-level symbol state are reused intraday to reduce duplicate work.

## Why this reduces load and enables multi-strategy scale
The scanner shifts work to pre-open/prep windows, minimizes repeated intraday full recomputation, and relies on deterministic cache invalidation and delta processing. This reduces provider/API load (including IBKR snapshot pressure) and keeps runtime headroom for future multi-strategy orchestration.
