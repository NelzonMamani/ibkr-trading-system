import sys

sys.path.append("src")

from config.runtime_config import RunMode, RuntimeConfig
from core.active_trade_registry import ActiveTradeRegistry
from core.event_collector import EventCollector
from core.replay_engine import ReplayEngine
from execution.execution_engine import ExecutionEngine
from execution.trade_exit_engine import TradeExitEngine
from execution.order_gateway import OrderGateway, GatewayDecision
from execution.liquidity_model import LiquidityModel
from models.data_models import RiskDecision
from config.config_resolver import set_config_overrides


def _build_risk_decision(symbol: str, trader_type: str, quantity: int) -> RiskDecision:
    entry_price = 10.0
    decision = RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=quantity,
        risk_level="LOW",
        rationale="test",
        trader_type=trader_type,
        strategy_name="UnitTestStrategy",
        direction="LONG",
        stop_loss_price=round(entry_price * 0.99, 4),
        decision_id=f"decision-{symbol}-{trader_type}",
    )
    decision.entry_price = entry_price
    return decision


def test_deterministic_liquidity_outcomes_and_replay():
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        registry = ActiveTradeRegistry()
        events = EventCollector()
        execution_engine = ExecutionEngine(trade_registry=registry, event_collector=events)
        exit_engine = TradeExitEngine(trade_registry=registry, event_collector=events)

        liquidity = LiquidityModel()
        gateway = OrderGateway()
        symbol = "XYZ"
        trader_type = "SCALPER"

        # Determine deterministic ticks for specific liquidity outcomes.
        tick_zero = next(
            tick
            for tick in range(1, 20)
            if liquidity.available_liquidity(symbol, tick, trader_type) == 0
            and gateway.decide(symbol, tick, trader_type, 1) == GatewayDecision.ACCEPT
        )
        tick_one = next(
            tick
            for tick in range(1, 20)
            if liquidity.available_liquidity(symbol, tick, trader_type) == 1
            and gateway.decide(symbol, tick, trader_type, 1) == GatewayDecision.ACCEPT
        )

        # FULL fill
        execution_engine.current_tick = tick_one
        full_decision = _build_risk_decision(symbol, trader_type, quantity=1)
        full_result = execution_engine.execute_trade(full_decision)

        assert full_result.fill_status == "FULL"
        assert full_result.filled_quantity == 1
        assert full_result.remaining_quantity == 0
        assert full_result.requested_quantity == 1
        assert registry.count_active_by_trader(trader_type) == 1

        exit_results, _ = exit_engine.evaluate_and_close_trades(
            run_mode=RunMode.PAPER,
            tick=tick_one + 20,
            config=RuntimeConfig(min_hold_ticks=0, max_hold_ticks=1),
        )
        assert exit_results, "Full fill should produce a closing execution result"
        assert registry.count_active_by_trader(trader_type) == 0

        # PARTIAL fill
        execution_engine.current_tick = tick_one
        partial_decision = _build_risk_decision(symbol, trader_type, quantity=2)
        partial_result = execution_engine.execute_trade(partial_decision)

        assert partial_result.fill_status == "PARTIAL"
        assert partial_result.filled_quantity == 1
        assert partial_result.remaining_quantity == 1
        assert partial_result.requested_quantity == 2
        assert partial_result.note is not None
        assert registry.count_active_by_trader(trader_type) == 1

        exit_results, _ = exit_engine.evaluate_and_close_trades(
            run_mode=RunMode.PAPER,
            tick=tick_one + 22,
            config=RuntimeConfig(min_hold_ticks=0, max_hold_ticks=1),
        )
        assert exit_results[0].gross_realised_pnl > 0
        assert exit_results[0].filled_quantity == 1
        assert registry.count_active_by_trader(trader_type) == 0

        # NONE (no fill)
        execution_engine.current_tick = tick_zero
        none_decision = _build_risk_decision(symbol, trader_type, quantity=1)
        none_result = execution_engine.execute_trade(none_decision)

        assert none_result.fill_status == "NONE"
        assert none_result.filled_quantity == 0
        assert none_result.remaining_quantity == 1
        assert registry.count_active_by_trader(trader_type) == 0

        # Replay should respect emitted events (no recomputation of liquidity).
        replay = ReplayEngine()
        replay.replay(events.snapshot_all())
    finally:
        set_config_overrides(None)
