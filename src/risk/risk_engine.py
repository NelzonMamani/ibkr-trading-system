"""
Teaching-first risk engine that deterministically converts intents to risk decisions.

Phase 4: Minimal live-capable scaffolding with highly constrained, conservative defaults.
"""

from models.data_models import RiskDecision, TradeIntent
from portfolio.active_trade_registry import active_trade_registry


class RiskEngine:
    """Minimal risk engine placeholder with teaching-style log messages."""

    def __init__(self) -> None:
        print("[BOOT] RiskEngine instantiated — phase 4 teaching rules active")
        self.strategy_limits = {
            "SCALPER": {
                "max_trades": 2,
            },
            "MOMENTUM": {
                "max_trades": 1,
            },
        }

    def evaluate_trade_intent(self, trade_intent: TradeIntent) -> RiskDecision:
        """
        Evaluate a TradeIntent using deterministic, conservative rules.

        Always returns a RiskDecision to keep the classroom flow moving without
        performing portfolio math, order routing, or broker interactions.
        """

        print(f"[RISK] Evaluating TradeIntent for symbol={trade_intent.symbol}")

        trader_type = getattr(trade_intent, "trader_type", "MANUAL").upper()
        strategy_name = getattr(trade_intent, "strategy_name", "UNKNOWN")
        current_active_strategy = active_trade_registry.count_active_by_strategy(strategy_name)
        current_active_trader = active_trade_registry.count_active_by_trader_type(trader_type)
        strategy_limit = self.strategy_limits.get(trader_type)
        if strategy_limit:
            max_trades = strategy_limit.get("max_trades", 0)
            print(
                f"[RISK:STRATEGY] current_active_by_strategy={current_active_strategy} "
                f"current_active_by_trader_type={current_active_trader} max={max_trades}"
            )
            if current_active_trader >= max_trades:
                print(
                    f"[RISK:STRATEGY] {trader_type} active={current_active_trader} max={max_trades} "
                    "→ BLOCKED (limit reached)"
                )
                rationale = (
                    f"Strategy {trader_type} reached its max active trades "
                    f"({current_active_trader}/{max_trades}); blocking this intent using real open trades."
                )
                return RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    strategy_name=strategy_name,
                    direction=trade_intent.direction,
                    trader_type=trader_type,
                )

            print(
                f"[RISK:STRATEGY] {trader_type} active={current_active_trader} max={max_trades} "
                "→ ALLOW (within limit)"
            )
        else:
            print(
                f"[RISK:STRATEGY] {trader_type} has no configured limit — defaulting to ALLOW"
            )

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
            f"and set risk level to {risk_level} based on confidence for {trader_type} within strategy limits. "
            "ActiveTradeRegistry used for real-time limits."
        )

        return RiskDecision(
            symbol=trade_intent.symbol,
            allowed=allowed,
            max_position_size=max_position_size,
            risk_level=risk_level,
            rationale=rationale,
            strategy_name=strategy_name,
            direction=trade_intent.direction,
            trader_type=trader_type,
        )
