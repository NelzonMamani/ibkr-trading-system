PHASE 1 — STRATEGY POLICY CANONICALIZATION

File:
src/strategies/ross_momentum/strategy_policy.py

Actions:
- Define StockSelectionSpec with ALL scanner gate variables:
  universe_source
  exchange_allowlist
  top_gainers_n
  watchlist_limit_k
  focus_limit_m
  price_min / price_max
  gap_min_pct / gap_max_pct
  rvol_min
  float_max_millions
  min_volume
  min_premarket_volume
  liquidity_min_dollar_volume
  spread_max_pct
  require_catalyst
  allow_halts
  allow_ssr
  data_quality_require_price
  data_quality_require_bid_ask
  max_symbols_per_cycle
  session_allowlist

Rules:
- No defaults outside this file
- Dataclass frozen=True
