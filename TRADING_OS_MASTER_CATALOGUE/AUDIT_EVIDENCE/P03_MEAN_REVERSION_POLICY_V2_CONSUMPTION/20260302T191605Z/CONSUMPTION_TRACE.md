# CONSUMPTION_TRACE

## Runtime call-site trace
```
65:    FocusBuilderV2,
66:    RankingEngineV2,
67:    SelectionEngineV2,
68:    WatchlistBuilderV2,
73:from src.strategy_policy_v2.registry import resolve_policy_v2
872:        policy_v2 = resolve_policy_v2(self.selected_strategy_key)
883:        selection = SelectionEngineV2().evaluate(policy, adapted)
884:        ranking = RankingEngineV2().rank(policy, selection.eligible)
885:        watchlist_symbols = {item.get("symbol", "") for item in WatchlistBuilderV2().build(policy, ranking.ranked).watchlist}
886:        focus_symbols = {item.get("symbol", "") for item in FocusBuilderV2().build(policy, ranking.ranked).focus}
```

## Deterministic dry-run
- strategy_id: P03
- eligible_count: 2
- dropped_count: 1
- watchlist_symbols: ['MRV1', 'MRV2']
- focus_symbols: ['MRV1', 'MRV2']
