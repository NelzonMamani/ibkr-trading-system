# ROSS_MOMENTUM_CONSTITUTION.md

**Status:** IMMUTABLE (constitution). Any change requires a version bump and explicit review.

## 1) What this strategy is
An intraday U.S. equity momentum strategy that:
- Trades a curated set of **in-play** tickers (gap + relative volume + liquidity + catalyst/attention).
- Executes a finite family of momentum setups (breakouts and pullbacks).
- Scales out and protects gains with systematic partials and trailing.
- Stops when conditions degrade (daily max loss, repeated fails, topping behaviour).

## 2) Core universals (apply to all setups)
### Stock is “in-play”
Minimum constraints (tunable in Policy; constitution fixes the *presence* of these gates):
- Price range appropriate for momentum trading; exclude illiquid penny/OTC.
- Relative volume / unusual volume present.
- Sufficient intraday liquidity (prints, spread, depth).
- Clear nearby levels (pre-market high/low, prior day levels).

### Timeframe roles
- Daily: context, major support/resistance, 50/200 EMA proximity.
- 5-min: setup validation and trend/structure.
- 1-min: entry structure, topping/tail risk detection.
- 10-sec: execution for fast entries and micro-pullback re-entries.

### Risk invariants
- Trade only when system “Trade Permission Matrix” permits.
- Hard max loss / kill-switch respected.
- One symbol: do not pyramid blindly; adds require pullback structure.

## 3) Setup families (high level)
The complete setup catalogue is defined in `SETUP_FAMILIES_AND_PATTERNS.md` and is normative.

## 4) Policy and implementation
- Machine-readable rules live in `strategy_policy.py` (Strategy Policy).
- Required live inputs are defined in `strategy_context_schema.py` (Strategy Context schema).
- Event semantics and trade permission are defined in `TRADE_PERMISSION_MATRIX.md`.

## 5) Done definition
“Done” means: given the required context, the strategy produces the same categories of actions a trained Ross-style trader would take: **scan → select in-play → enter → add on pullbacks → partials → trail → exit → pause/stop on danger**.
