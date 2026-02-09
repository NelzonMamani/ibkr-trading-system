import sys

sys.path.append("src")

from execution.execution_engine import ExecutionEngine
from execution.order_gateway import GatewayDecision, OrderGateway
from execution.liquidity_model import LiquidityModel
from models.data_models import RiskDecision
from core.active_trade_registry import ActiveTradeRegistry
from core.event_collector import EventCollector
from config.config_resolver import set_config_overrides


def _risk(symbol: str, trader_type: str, qty: int) -> RiskDecision:
    return RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=qty,
        risk_level="LOW",
        rationale="test",
        trader_type=trader_type,
        strategy_name="UnitTestStrategy",
        direction="LONG",
        decision_id=f"decision-{symbol}-{trader_type}",
    )


def _find_tick_for_decision(symbol: str, trader_type: str, decision: GatewayDecision):
    gateway = OrderGateway()
    for tick in range(1, 50):
        if gateway.decide(symbol, tick, trader_type, 1) == decision:
            return tick
    raise AssertionError("No tick found for requested decision in range")


def test_gateway_rejections_and_retries():
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        registry = ActiveTradeRegistry()
        events = EventCollector()
        execution_engine = ExecutionEngine(trade_registry=registry, event_collector=events)
        liquidity = LiquidityModel()
        gateway = OrderGateway()
        symbol = "ABC"
        trader_type_scalper = "SCALPER"
        trader_type_momo = "MOMENTUM"

        hard_tick = _find_tick_for_decision(symbol, trader_type_scalper, GatewayDecision.REJECT)
        execution_engine.current_tick = hard_tick
        hard_result = execution_engine.execute_trade(_risk(symbol, trader_type_scalper, 1))
        assert hard_result.gateway_decision == GatewayDecision.REJECT.value
        assert hard_result.rejection_reason == "GATEWAY_HARD_REJECT"
        assert hard_result.retry_scheduled is False
        assert execution_engine.pending_book.count() == 0

        soft_accept_tick = next(
            tick
            for tick in range(1, 50)
            if gateway.decide(symbol, tick, trader_type_momo, 1) == GatewayDecision.SOFT_REJECT
            and gateway.decide(symbol, tick + 1, trader_type_momo, 2) == GatewayDecision.ACCEPT
            and liquidity.available_liquidity(symbol, tick + 1, trader_type_momo) > 0
        )
        execution_engine.current_tick = soft_accept_tick
        initial_soft = execution_engine.execute_trade(_risk(symbol, trader_type_momo, 1))
        assert initial_soft.retry_scheduled is True
        next_tick_results = execution_engine.process_pending_orders(soft_accept_tick + 1)
        assert next_tick_results, "Retry should be processed"
        retry_result = next_tick_results[0]
        assert retry_result.gateway_decision == GatewayDecision.ACCEPT.value
        assert retry_result.fill_status in {"FULL", "PARTIAL"}
        assert registry.count_active_by_trader(trader_type_momo) == 1

        expire_tick = next(
            tick
            for tick in range(1, 50)
            if gateway.decide(symbol, tick, trader_type_scalper, 1) == GatewayDecision.SOFT_REJECT
            and gateway.decide(symbol, tick + 1, trader_type_scalper, 2) == GatewayDecision.SOFT_REJECT
        )
        execution_engine.current_tick = expire_tick
        first_attempt = execution_engine.execute_trade(_risk(symbol, trader_type_scalper, 1))
        assert first_attempt.retry_scheduled is True
        expire_results = execution_engine.process_pending_orders(expire_tick + 1)
        assert expire_results, "Second attempt should produce a result"
        expire_result = expire_results[0]
        assert expire_result.status == "EXPIRED"
        assert expire_result.rejection_reason == "EXPIRED"
        assert execution_engine.pending_book.count() == 0
    finally:
        set_config_overrides(None)
