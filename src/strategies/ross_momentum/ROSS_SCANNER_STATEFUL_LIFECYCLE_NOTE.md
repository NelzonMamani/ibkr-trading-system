# Ross Scanner Stateful Lifecycle Note

## Daily list model
Ross scanner now maintains explicit daily lists for:
- `TOP_UNIVERSE` (broad tracked symbols/ranks)
- `WATCHLIST_K` (symbols passing stock-selection)
- `FOCUS_M` (active setup monitoring list)
- `REJECTED_TRACKED` (rejections cached with reason/staleness)

Daily state resets explicitly at trading-day/session boundaries and is logged.

## Session-aware metric contract (authoritative runtime intent)
- Main Ross `pct_change` gate uses `LAST_RTH_CLOSE` in `PRE`, `RTH`, and `AH`.
- `open_relative_pct_change` is optional secondary telemetry and must never silently replace main Ross gating.
- In `OVN` / `CLOSED` / weekend conditions, percent change is persisted last-session context (`baseline=LAST_SESSION_REFERENCE`) and is prep/ranking metadata, not an RTH live trigger.
- RVOL is session-normalized in `PRE`/`RTH`/`AH`; in closed sessions it uses persisted provenance (`method=PERSISTED_RVOL`) or explicit unavailable semantics.
- Provenance fields are mandatory for operator explainability: `reference_label`, `pct_source`, `rvol_baseline`, `rvol_method`.

## Prep lifecycle contract
- `CLOSED` / `AH` / `OVN` / weekend: prep is allowed to run, refresh candidate state, and build tomorrow-readiness artifacts without requiring heavy live-trading gates.
- `PRE`: prep cadence increases and enriches watchlist/focus candidates for premarket and open participation.
- `RTH`: trading is primary; prep remains non-blocking maintenance/hydration.
- Prep artifact persistence includes last valid session metrics (`persisted_pct_change`, `persisted_rvol`, `persisted_volume`) plus provenance metadata/timestamps.

## Distinction of metadata roles
- **Prep ranking metadata:** supports scheduling, operator visibility, and candidate continuity.
- **Live scanner gating metadata:** enforces session-appropriate tradability checks.
- **Setup/execution eligibility:** remains strategy/pattern/risk-layer authority and is not inferred solely from prep persistence.

## Troubleshooting log map
Operators should use these log families to verify provenance and lifecycle behavior:
- `[PCT_DEBUG] symbol=... session=... reference=... last_price=... reference_price=... pct_change=...`
- `[RVOL_DEBUG] symbol=... session=... current_volume=... expected_volume=... rvol=...`
- `[PCT] symbol=... session=CLOSED baseline=LAST_SESSION_REFERENCE value=...`
- `[RVOL] symbol=... session=CLOSED baseline=LAST_SESSION_REFERENCE method=PERSISTED_RVOL value=...`
- `[PREP] mode=... prepared_symbols=...`
- `[PREP] hydrate ok path=... restored_symbols=...`

## Cache/reuse policy
- Float cache is reused per-day with hit/lookup logging and daily invalidation.
- News enrichment cache is reused by signature and emits `news_changed` diagnostics.
- Rejection decisions are tracked and reused until stale/materially changed.
- Prep outputs and day-level symbol state are reused intraday to reduce duplicate work.

## Why this reduces load and enables multi-strategy scale
The scanner shifts work to pre-open/prep windows, minimizes repeated intraday full recomputation, and relies on deterministic cache invalidation and delta processing. This reduces provider/API load (including IBKR snapshot pressure) and keeps runtime headroom for future multi-strategy orchestration.
