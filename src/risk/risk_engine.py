"""
Teaching-first risk engine that deterministically converts intents to risk decisions.

Phase 4: Minimal live-capable scaffolding with highly constrained, conservative defaults.
"""

from models.data_models import RiskDecision, TradeIntent


class RiskEngine:
    """Minimal risk engine placeholder with teaching-style log messages."""

    def __init__(self) -> None:
        print("[BOOT] RiskEngine instantiated — phase 4 teaching rules active")

    def evaluate_trade_intent(self, trade_intent: TradeIntent) -> RiskDecision:
        """
        Evaluate a TradeIntent using deterministic, conservative rules.

        Always returns a RiskDecision to keep the classroom flow moving without
        performing portfolio math, order routing, or broker interactions.
        """

        print(f"[RISK] Evaluating TradeIntent for symbol={trade_intent.symbol}")

        allowed = True
        if trade_intent.direction.upper() == "LONG":
            print("[RISK] Trade direction is LONG — teaching rule allows the idea to proceed")
            allowed = True
        else:
            print(
                "[RISK] Trade direction is not LONG — still allowed for teaching; "
                "no blocking logic implemented"
            )

        max_position_size = 1
        print("[RISK] Max position size capped at 1 share for safety and simplicity")

        confidence = trade_intent.confidence
        if confidence >= 0.75:
            risk_level = "LOW"
            print("[RISK] Confidence >= 0.75 — assigning risk level LOW for teaching clarity")
        elif confidence >= 0.50:
            risk_level = "MEDIUM"
            print("[RISK] Confidence between 0.50 and 0.74 — assigning risk level MEDIUM")
        else:
            risk_level = "HIGH"
            print("[RISK] Confidence < 0.50 — assigning risk level HIGH to emphasize caution")

        rationale = (
            "Teaching-only decision: allow intent, cap size at 1 share, "
            f"and set risk level to {risk_level} based on confidence."
        )

        return RiskDecision(
            symbol=trade_intent.symbol,
            allowed=allowed,
            max_position_size=max_position_size,
            risk_level=risk_level,
            rationale=rationale,
        )
