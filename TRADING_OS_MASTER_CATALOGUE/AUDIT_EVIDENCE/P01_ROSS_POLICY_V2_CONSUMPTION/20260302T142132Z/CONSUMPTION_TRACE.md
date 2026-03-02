# CONSUMPTION_TRACE

## Runtime call-site trace
```
67:    SelectionEngineV2,
71:from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2 as ROSS_POLICY_V2
870:        raw = get_config("STRATEGY_POLICY_V2_ENABLED")
875:    def _build_watchlist_focus_v2(self, observations: list[CandidateMetrics]) -> tuple[list[CandidateMetrics], list[CandidateMetrics]]:
877:        selection = SelectionEngineV2().evaluate(ROSS_POLICY_V2, adapted)
878:        ranking = RankingEngineV2().rank(ROSS_POLICY_V2, selection.eligible)
879:        watchlist_symbols = {item.get("symbol", "") for item in WatchlistBuilderV2().build(ROSS_POLICY_V2, ranking.ranked).watchlist}
880:        focus_symbols = {item.get("symbol", "") for item in FocusBuilderV2().build(ROSS_POLICY_V2, ranking.ranked).focus}
979:            watchlist, focus_rows = self._build_watchlist_focus_v2(observations)
```

## Deterministic dry-run
- eligible_count: 2
- dropped_count: 1
- watchlist_symbols: ['AAA', 'BBB']
- focus_symbols: ['AAA', 'BBB']
