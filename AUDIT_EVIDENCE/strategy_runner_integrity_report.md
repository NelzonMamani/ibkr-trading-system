# Strategy Runner Integrity Report

Generated at: `2026-03-04T11:37:20.516198+00:00`

| Strategy | Expected runner file exists | Import class | Execution | Result shape |
|---|---:|---|---:|---|
| P01 Ross Momentum | False | `src.strategies.ross_momentum_strategy_v1.RossMomentumStrategyV1` | True | `list` |
| P02 Statistical Intraday Momentum | False | `src.strategies.statistical_intraday_momentum.strategy.StatisticalIntradayMomentum` | True | `list` |
| P03 Mean Reversion | False | `src.strategies.mean_reversion.strategy.MeanReversionStrategy` | True | `list` |
| P04 Long Horizon Value | True | `src.strategies.long_horizon_value.runner.LongHorizonValueRunner` | True | `dict` |

## Notes
- P01/P02/P03 explicit `runner.py` modules are not present at the specified paths; runtime uses strategy adapters wired through `StrategyRunner.process_watchlist`.
- Import, instantiation, and adapter execution all completed without runtime crashes for all four strategies.
