"""
Teaching-first risk engine that deterministically converts intents to risk decisions.

Phase 4: Minimal live-capable scaffolding with highly constrained, conservative defaults.
"""

from typing import Optional

from src.config.config_resolver import get_config
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.models.data_models import RiskDecision, TradeIntent
from src.models.risk_decision import DATA_QUALITY_BLOCK, STRATEGY_LIMIT_REACHED
from strategies.ross_momentum.ross_momentum_risk_overlay import (
    RiskContext,
    RossMomentumRiskOverlay,
)


class RiskEngine:
    """Minimal risk engine placeholder with teaching-style log messages."""

    def __init__(
        self,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
    ) -> None:
        print("[BOOT] RiskEngine instantiated — phase 4 teaching rules active")
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.ross_overlay = RossMomentumRiskOverlay(event_collector=self.event_collector)
        self._ross_strategy_names = {
            "MomentumContinuationStrategy",
            "RossMomentumStrategy",
            "RossMomentumStrategyV1",
        }
        self.strategy_limits = dict(get_config("RISK_STRATEGY_LIMITS"))

    def evaluate_trade_intent(self, trade_intent: TradeIntent) -> RiskDecision:
        """
        Evaluate a TradeIntent using deterministic, conservative rules.

        Always returns a RiskDecision to keep the classroom flow moving without
        performing portfolio math, order routing, or broker interactions.
        """

        print(f"[RISK] Evaluating TradeIntent for symbol={trade_intent.symbol}")

        data_quality_flags = getattr(trade_intent, "data_quality_flags", [])
        if data_quality_flags:
            rationale = (
                "Trade intent blocked due to data quality flags: "
                + ", ".join(data_quality_flags)
            )
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="RiskEngine",
                payload={
                    "symbol": trade_intent.symbol,
                    "trader_type": trade_intent.trader_type,
                    "strategy_name": trade_intent.strategy_name,
                    "reason": DATA_QUALITY_BLOCK,
                    "reason_code": DATA_QUALITY_BLOCK,
                    "human_readable_rationale": rationale,
                },
            )
            print(
                "[RISK] Data quality block — "
                f"symbol={trade_intent.symbol} flags={data_quality_flags}"
            )
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=DATA_QUALITY_BLOCK,
            )

        if trade_intent.strategy_name in self._ross_strategy_names:
            overlay_context = RiskContext(
                current_tick=getattr(trade_intent, "tick", 0) or 0
            )
            overlay_decision = self.ross_overlay.evaluate(trade_intent, overlay_context)
            if overlay_decision is not None:
                return overlay_decision

        trader_type = getattr(trade_intent, "trader_type", "MANUAL").upper()
        current_active = self.trade_registry.count_active_by_trader(trader_type)
        print(
            f"[RISK:REGISTRY] Active trades for {trader_type} currently {current_active} "
            "(registry single source of truth)"
        )
        strategy_limit = self.strategy_limits.get(trader_type)
        if strategy_limit:
            max_trades = strategy_limit.get("max_trades", 0)
            if current_active >= max_trades:
                print(
                    f"[RISK:STRATEGY] {trader_type} active={current_active} max={max_trades} "
                    "→ BLOCKED (limit reached)"
                )
                self.event_collector.emit(
                    event_type="TRADE_BLOCKED",
                    source="RiskEngine",
                    payload={
                        "symbol": trade_intent.symbol,
                        "trader_type": trade_intent.trader_type,
                        "strategy_name": trade_intent.strategy_name,
                        "reason": STRATEGY_LIMIT_REACHED,
                        "reason_code": STRATEGY_LIMIT_REACHED,
                        "human_readable_rationale": (
                            f"Strategy {trader_type} reached its max active trades "
                            f"({current_active}/{max_trades}); blocking this intent."
                        ),
                    },
                )
                print(
                    f"[EVENT] TRADE_BLOCKED emitted for "
                    f"{trade_intent.symbol} ({trade_intent.trader_type})"
                )
                rationale = (
                    f"Strategy {trader_type} reached its max active trades "
                    f"({current_active}/{max_trades}); blocking this intent."
                )
                return RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code=STRATEGY_LIMIT_REACHED,
                )

            print(
                f"[RISK:STRATEGY] {trader_type} active={current_active} max={max_trades} "
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

        max_position_size = int(get_config("RISK_MAX_POSITION_SIZE"))
        print(
            "[RISK] Max position size capped at "
            f"{max_position_size} share(s) for safety and simplicity"
        )

        confidence = trade_intent.confidence
        low_threshold = float(get_config("RISK_CONFIDENCE_LOW_THRESHOLD"))
        medium_threshold = float(get_config("RISK_CONFIDENCE_MEDIUM_THRESHOLD"))
        if confidence >= low_threshold:
            risk_level = "LOW"
            print(
                f"[RISK] Confidence >= {low_threshold:.2f} — assigning risk level LOW for teaching clarity"
            )
        elif confidence >= medium_threshold:
            risk_level = "MEDIUM"
            print(
                f"[RISK] Confidence between {medium_threshold:.2f} and {low_threshold:.2f} — "
                "assigning risk level MEDIUM"
            )
        else:
            risk_level = "HIGH"
            print(
                f"[RISK] Confidence < {medium_threshold:.2f} — assigning risk level HIGH to emphasize caution"
            )

        rationale = (
            "Teaching-only decision: allow intent, cap size at 1 share, "
            f"and set risk level to {risk_level} based on confidence for {trader_type} "
            "within strategy limits."
        )

        return RiskDecision(
            symbol=trade_intent.symbol,
            allowed=allowed,
            max_position_size=max_position_size,
            risk_level=risk_level,
            rationale=rationale,
            trader_type=trader_type,
            strategy_name=trade_intent.strategy_name,
            direction=trade_intent.direction,
            stop_loss_price=getattr(trade_intent, "stop_loss_price", None),
            take_profit_price=getattr(trade_intent, "take_profit_price", None),
            pattern_name=getattr(trade_intent, "pattern_name", None),
            invalidation_level=getattr(trade_intent, "invalidation_level", None),
        )
