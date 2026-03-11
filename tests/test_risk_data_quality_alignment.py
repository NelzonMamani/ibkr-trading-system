from src.config.config_resolver import set_config_overrides
from src.core.stop_controller import StopController
from src.risk.risk_engine import RiskEngine
from src.strategies.strategy_contracts import (
    DecisionType,
    Direction,
    StrategyRiskPayload,
    TimeInForcePolicy,
    TradeIntent,
)


def _payload(*, flags: list[str]) -> StrategyRiskPayload:
    return StrategyRiskPayload(
        strategy_id="RossMomentumStrategy",
        symbol="CYN",
        intents=[
            TradeIntent(
                intent_id="cyn-1",
                symbol="CYN",
                direction=Direction.LONG,
                entry_model="MKT",
                stop_model="STRUCTURE",
                target_model=None,
                time_in_force_policy=TimeInForcePolicy.DAY,
                invalidations=[],
                rationale_text="test",
                risk_flags=flags,
            )
        ],
        decision_type=DecisionType.EMIT_INTENT,
        confidence=0.9,
        rationale_text="test",
        risk_flags=[],
    )


def test_live_intent_not_blocked_for_nonblocking_data_quality_flags() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True})
    try:
        engine = RiskEngine(stop_controller=StopController())
        decision = engine.evaluate_strategy_payload(_payload(flags=["NEWS_DELAYED"]))
        assert decision.overall_action == "ALLOW"
        assert decision.per_intent[0].allowed is True
    finally:
        set_config_overrides(None)


def test_live_intent_blocked_for_missing_bid_ask_flag() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True})
    try:
        engine = RiskEngine(stop_controller=StopController())
        decision = engine.evaluate_strategy_payload(_payload(flags=["DROP_MISSING_BID_ASK"]))
        assert decision.overall_action == "BLOCK"
        assert "DATA_QUALITY_BLOCK" in decision.per_intent[0].reason_tags
    finally:
        set_config_overrides(None)
