__all__ = [
    "EarlyEntryMomentumStrategy",
    "RetailConfirmationMomentumStrategy",
    "RossMomentumStrategyV1",
]


def __getattr__(name: str):
    if name == "EarlyEntryMomentumStrategy":
        from src.strategies.early_entry_momentum.strategy import EarlyEntryMomentumStrategy

        return EarlyEntryMomentumStrategy
    if name == "RetailConfirmationMomentumStrategy":
        from src.strategies.ross_momentum.strategy import RetailConfirmationMomentumStrategy

        return RetailConfirmationMomentumStrategy
    if name == "RossMomentumStrategyV1":
        from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1

        return RossMomentumStrategyV1
    raise AttributeError(f"module 'src.strategies' has no attribute {name}")
