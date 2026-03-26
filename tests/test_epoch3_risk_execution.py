from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.config_resolver import set_config_overrides  # noqa: E402
from config.runtime_config import RunMode  # noqa: E402
from core.active_trade_registry import ActiveTrade, ActiveTradeRegistry  # noqa: E402
from core.event_collector import EventCollector  # noqa: E402
from core.stop_controller import StopController  # noqa: E402
from execution.execution_engine import ExecutionEngine  # noqa: E402
from risk.risk_engine import RiskEngine  # noqa: E402
from strategies.strategy_contracts import (  # noqa: E402
    DecisionType,
    Direction,
    StrategyRiskPayload,
    TimeInForcePolicy,
    TradeIntent,
)


def _intent(intent_id: str, symbol: str) -> TradeIntent:
    return TradeIntent(
        intent_id=intent_id,
        symbol=symbol,
        direction=Direction.LONG,
        entry_model="MKT",
        stop_model="STRUCTURE",
        target_model=None,
        time_in_force_policy=TimeInForcePolicy.DAY,
        invalidations=[],
        rationale_text="unit-test",
        risk_flags=[],
    )


def _payload(intent_id: str = "intent-1", symbol: str = "ABC") -> StrategyRiskPayload:
    return StrategyRiskPayload(
        strategy_id="UnitTestStrategy",
        symbol=symbol,
        intents=[_intent(intent_id, symbol)],
        decision_type=DecisionType.EMIT_INTENT,
        confidence=0.9,
        rationale_text="unit-test",
        risk_flags=[],
    )


def _attach_decision_id(decision, decision_id: str) -> None:
    decision.decision_id = decision_id
    entry_price = getattr(decision, "entry_price", None) or 10.0
    decision.entry_price = entry_price
    if getattr(decision, "stop_loss_price", None) is None:
        decision.stop_loss_price = round(float(entry_price) * 0.99, 4)


def test_risk_engine_blocks_live_read_only():
    set_config_overrides({"RUN_MODE": "READ_ONLY", "EXECUTION_ENABLED": True})
    try:
        stop_controller = StopController()
        risk_engine = RiskEngine(stop_controller=stop_controller)
        decision = risk_engine.evaluate_strategy_payload(_payload())
        _attach_decision_id(decision, "decision-readonly")

        assert decision.overall_action == "BLOCK"
        assert decision.per_intent
        assert decision.per_intent[0].allowed is False
        assert "LIVE_READ_ONLY_BLOCK" in decision.per_intent[0].reason_tags
    finally:
        set_config_overrides(None)


def test_paper_pipeline_runs_without_broker_routing():
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        stop_controller = StopController()
        risk_engine = RiskEngine(stop_controller=stop_controller)
        decision = risk_engine.evaluate_strategy_payload(_payload())
        _attach_decision_id(decision, "decision-paper")

        registry = ActiveTradeRegistry()
        events = EventCollector()
        engine = ExecutionEngine(
            trade_registry=registry,
            event_collector=events,
            stop_controller=stop_controller,
        )

        engine.current_tick = 10
        result = engine.execute_trade(decision)

        assert engine.broker is not None
        assert engine.broker.is_live() is False
        assert result.status in {"SIMULATED", "REJECTED", "EXPIRED", "BLOCKED", "PARTIAL", "FULL"}
    finally:
        set_config_overrides(None)


def test_live_read_only_blocks_execution_engine():
    set_config_overrides({"RUN_MODE": "READ_ONLY", "EXECUTION_ENABLED": True})
    try:
        stop_controller = StopController()
        risk_engine = RiskEngine(stop_controller=stop_controller)
        decision = risk_engine.evaluate_strategy_payload(_payload())
        _attach_decision_id(decision, "decision-readonly")

        events = EventCollector()
        engine = ExecutionEngine(event_collector=events, stop_controller=stop_controller)
        engine.run_mode = RunMode.READ_ONLY

        result = engine.execute_trade(decision)

        assert result.status == "BLOCKED"
        assert events.count("ORDER_SUBMITTED") == 0
    finally:
        set_config_overrides(None)


def test_idempotency_prevents_duplicate_submissions():
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        stop_controller = StopController()
        risk_engine = RiskEngine(stop_controller=stop_controller)
        decision = risk_engine.evaluate_strategy_payload(_payload(intent_id="dup-1"))
        _attach_decision_id(decision, "decision-dup")

        events = EventCollector()
        engine = ExecutionEngine(event_collector=events, stop_controller=stop_controller)
        engine.current_tick = 42

        first = engine.execute_trade(decision)
        second = engine.execute_trade(decision)

        assert first.status != "DUPLICATE"
        assert second.status == "DUPLICATE"
        assert events.count("ORDER_SUBMITTED") == 1
    finally:
        set_config_overrides(None)


def test_execution_blocks_when_breaker_tripped():
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        stop_controller = StopController()
        stop_controller.trip_breaker(
            breaker_id="DAILY_LOSS_LIMIT",
            reason="Daily loss breached",
            source="unit-test",
        )

        risk_engine = RiskEngine(stop_controller=stop_controller)
        decision = risk_engine.evaluate_strategy_payload(_payload())
        _attach_decision_id(decision, "decision-breaker")

        engine = ExecutionEngine(stop_controller=stop_controller)
        engine.current_tick = 5
        result = engine.execute_trade(decision)

        assert result.status == "BLOCKED"
        assert "CIRCUIT_BREAKER" in result.rejection_reason
    finally:
        set_config_overrides(None)


def test_risk_engine_blocks_max_open_positions():
    set_config_overrides(
        {"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True, "RISK_MAX_OPEN_POSITIONS": 1}
    )
    try:
        registry = ActiveTradeRegistry()
        registry.register_trade(
            ActiveTrade(
                symbol="ABC",
                trader_type="MANUAL",
                entry_tick=1,
                entry_price=10.0,
                direction="LONG",
                quantity=1,
                strategy_name="UnitTestStrategy",
                stop_loss_price=9.5,
            )
        )
        risk_engine = RiskEngine(trade_registry=registry, stop_controller=StopController())
        decision = risk_engine.evaluate_strategy_payload(_payload())

        assert decision.overall_action == "BLOCK"
        assert "RISK_MAX_OPEN_POSITIONS" in decision.risk_reasons
    finally:
        set_config_overrides(None)
