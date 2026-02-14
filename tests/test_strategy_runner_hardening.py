from src.config.config_resolver import set_config_overrides
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.statistical_intraday_momentum.strategy import StatisticalIntradayMomentum


def test_strategy_runner_selected_strategy_runs_exactly_one() -> None:
    set_config_overrides(
        {
            "SELECTED_STRATEGY": "statistical_intraday_momentum",
            "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": True,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "MEAN_REVERSION_STRATEGY_ENABLED": True,
            "LONG_HORIZON_VALUE_STRATEGY_ENABLED": True,
        }
    )
    try:
        runner = StrategyRunner()
    finally:
        set_config_overrides({})

    assert len(runner.strategies) == 1
    assert isinstance(runner.strategies[0], StatisticalIntradayMomentum)


def test_strategy_runner_respects_enabled_strategies_contract_for_batch_a_entries() -> None:
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
