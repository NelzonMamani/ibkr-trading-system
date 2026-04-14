from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.config_resolver import set_config_overrides  # noqa: E402
from core.active_trade_registry import ActiveTrade, ActiveTradeRegistry  # noqa: E402
from core.event_collector import EventCollector  # noqa: E402
from core.stop_controller import StopController  # noqa: E402
from execution.execution_engine import ExecutionEngine  # noqa: E402
from execution.execution_providers import PositionSnapshot  # noqa: E402
from models.execution_result import ExecutionResult  # noqa: E402
from risk.risk_engine import RiskEngine  # noqa: E402
from strategies.strategy_contracts import (  # noqa: E402
    DecisionType,
    Direction,
    StrategyRiskPayload,
    TimeInForcePolicy,
    TradeIntent,
)


class _StartupRecoveryProvider:
    def __init__(self, positions: list[object]):
        self._positions = positions

    def name(self) -> str:
        return "STARTUP_RECOVERY_PROVIDER"

    def is_live(self) -> bool:
        return True

    def place_order(self, request):
        raise RuntimeError("not used in this test")

    def cancel(self, order_id: str):
        raise RuntimeError("not used in this test")

    def get_positions(self) -> PositionSnapshot:
        return PositionSnapshot(positions=self._positions, as_of="2026-03-26T00:00:00+00:00")

    def get_open_orders(self) -> list:
        return []


def _decision_without_stop(symbol: str = "AAPL"):
    payload = StrategyRiskPayload(
        strategy_id="UnitTestStrategy",
        symbol=symbol,
        intents=[
            TradeIntent(
                intent_id="intent-stop-test",
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
        ],
        decision_type=DecisionType.EMIT_INTENT,
        confidence=0.9,
        rationale_text="unit-test",
        risk_flags=[],
    )
    decision = RiskEngine(stop_controller=StopController()).evaluate_strategy_payload(payload)
    decision.decision_id = "decision-stop-test"
    decision.stop_loss_price = None
    return decision


def test_startup_recovery_restores_protected_position_once() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True})
    try:
        registry = ActiveTradeRegistry()
        recovered = ActiveTrade(
            symbol="MSFT",
            trader_type="MOMENTUM",
            entry_tick=100,
            entry_price=412.25,
            direction="LONG",
            quantity=3,
            strategy_name="UnitTestStrategy",
            stop_loss_price=409.50,
        )
        provider = _StartupRecoveryProvider([recovered])
        _ = ExecutionEngine(
            provider=provider,
            trade_registry=registry,
            event_collector=EventCollector(),
        )
        assert registry.count_active() == 1
        assert registry.get_trade("MSFT", "MOMENTUM") is not None
    finally:
        set_config_overrides(None)


def test_startup_recovery_flags_unprotected_position_and_skips_restore(capsys) -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True})
    try:
        registry = ActiveTradeRegistry()
        unprotected = SimpleNamespace(
            symbol="TSLA",
            trader_type="MOMENTUM",
            entry_tick=1,
            entry_price=180.0,
            direction="LONG",
            quantity=2,
            strategy_name="UnitTestStrategy",
            stop_loss_price=None,
        )
        provider = _StartupRecoveryProvider([unprotected])
        _ = ExecutionEngine(
            provider=provider,
            trade_registry=registry,
            event_collector=EventCollector(),
        )
        captured = capsys.readouterr().out
        assert "[CRITICAL][UNPROTECTED_POSITION]" in captured
        assert registry.count_active() == 0
    finally:
        set_config_overrides(None)


def test_execution_resolves_stop_loss_when_missing_in_paper_mode() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        engine = ExecutionEngine(event_collector=EventCollector(), stop_controller=StopController())
        engine.current_tick = 7
        result: ExecutionResult = engine.execute_trade(_decision_without_stop())
        assert result.stop_loss_price is not None
        assert result.status in {"SIMULATED", "REJECTED", "EXPIRED", "BLOCKED", "PARTIAL", "FULL", "NOT_FILLED"}
    finally:
        set_config_overrides(None)


def test_failsafe_blocks_new_entries() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        engine = ExecutionEngine(event_collector=EventCollector(), stop_controller=StopController())
        engine._failsafe_block_new_entries = True
        decision = _decision_without_stop("NVDA")
        decision.direction = "LONG"
        result: ExecutionResult = engine.execute_trade(decision)
        assert result.status == "BLOCKED"
        assert "FAILSAFE_BLOCK_NEW_ENTRIES" in str(result.rationale)
    finally:
        set_config_overrides(None)
