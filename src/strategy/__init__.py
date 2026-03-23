__all__ = ["RossMomentumStrategyV1"]


def __getattr__(name: str):
    if name == "RossMomentumStrategyV1":
        from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1

        return RossMomentumStrategyV1
    raise AttributeError(name)
