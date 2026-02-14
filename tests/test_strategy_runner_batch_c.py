from src.config.config_resolver import set_config_overrides
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.event_earnings_reaction.strategy import EventEarningsReactionStrategy


def test_strategy_runner_batch_c_selected_strategy_loads_exactly_one() -> None:
    set_config_overrides(
        {
            "SELECTED_STRATEGY": "event_earnings_reaction",
            "ENABLED_STRATEGIES": {
                "EventEarningsReactionStrategy": False,
                "EventNewsShockContinuationStrategy": False,
                "VolatilityContractionBreakoutStrategy": False,
                "VolatilityCarryRiskPremiumStrategy": False,
                "PairsDivergenceReversionStrategy": False,
            },
        }
    )
    try:
        runner = StrategyRunner()
    finally:
        set_config_overrides({})

    assert len(runner.strategies) == 1
    assert isinstance(runner.strategies[0], EventEarningsReactionStrategy)


def test_strategy_runner_batch_c_disabled_strategies_not_loaded() -> None:
    set_config_overrides(
        {
            "SELECTED_STRATEGY": "",
            "ENABLED_STRATEGIES": {
                "GapAndGoStrategy": False,
                "MomentumContinuationStrategy": False,
                "RossMomentumStrategyV1": False,
                "StatisticalIntradayMomentum": False,
                "MeanReversionStrategy": False,
                "LongHorizonValueStrategy": False,
                "EventEarningsReactionStrategy": False,
                "EventNewsShockContinuationStrategy": False,
                "VolatilityContractionBreakoutStrategy": False,
                "VolatilityCarryRiskPremiumStrategy": False,
                "PairsDivergenceReversionStrategy": False,
            },
            "ROSS_MOMENTUM_STRATEGY_ENABLED": False,
            "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": False,
            "MEAN_REVERSION_STRATEGY_ENABLED": False,
            "LONG_HORIZON_VALUE_STRATEGY_ENABLED": False,
        }
    )
    try:
        runner = StrategyRunner()
    finally:
        set_config_overrides({})

    assert runner.strategies == []
