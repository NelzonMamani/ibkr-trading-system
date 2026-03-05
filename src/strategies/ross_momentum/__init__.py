"""Ross Momentum strategy package."""

__all__ = ["RossMomentumRiskOverlay", "RossMomentumStrategy"]


def __getattr__(name: str):
    if name == "RossMomentumRiskOverlay":
        from src.strategies.ross_momentum.ross_momentum_risk_overlay import RossMomentumRiskOverlay

        return RossMomentumRiskOverlay
    if name == "RossMomentumStrategy":
        from src.strategies.ross_momentum.strategy import RossMomentumStrategy

        return RossMomentumStrategy
    raise AttributeError(name)
