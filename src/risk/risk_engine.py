"""
Risk engine skeleton responsible for approving or blocking trade intents.
"""

from models.data_models import RiskDecision, TradeIntent


class RiskEngine:
    """Skeleton risk engine returning placeholder decisions with logging."""

    def __init__(self) -> None:
        print("[BOOT] RiskEngine instantiated — skeleton only")

    def evaluate_trade_intent(self, trade_intent: TradeIntent) -> RiskDecision:
        """Evaluate a trade intent placeholder and return a neutral RiskDecision."""

        print("[RISK] Skeleton risk evaluation invoked — no logic implemented yet")
        return RiskDecision(trade_id=trade_intent.trade_id, risk_decision=None)
