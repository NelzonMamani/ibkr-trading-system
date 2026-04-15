from __future__ import annotations

from decimal import Decimal

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTrade
from src.core.orchestrator import CoreOrchestrator
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import PositionSnapshot
from src.execution.post_fill_lifecycle_engine import PositionLifecycleState
from src.models.data_models import RiskDecision
from src.models.execution_result import ExecutionResult


def _decision(*, qty: int = 1, symbol: str = "AAPL") -> RiskDecision:
    decision = RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=qty,
        risk_level="LOW",
        rationale="ok",
        trader_type="MANUAL",
        strategy_name="ross_momentum",
        direction="LONG",
        stop_loss_price=99.0,
        decision_id=f"decision-{symbol}",
        intent_id=f"intent-{symbol}",
    )
    decision.entry_price = 100.0
    return decision


def test_execution_blocks_invalid_qty_before_submit(capsys) -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        engine = ExecutionEngine()
        result = engine.execute_trade(_decision(qty=0))
    finally:
        set_config_overrides(None)

    assert result.attempted is False
    assert result.status == "BLOCKED"
    assert result.rationale == "INVALID_ORDER_QUANTITY"
    out = capsys.readouterr().out
    assert "[EXECUTION][PRECHECK]" in out
    assert "[EXECUTION][SUBMIT]" not in out


def test_execution_blocks_duplicate_open_position(capsys) -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        engine = ExecutionEngine()
        engine.trade_registry.register_trade(
            ActiveTrade(
                symbol="AAPL",
                trader_type="MANUAL",
                entry_tick=1,
                entry_price=100.0,
                direction="LONG",
                quantity=1,
                strategy_name="ross_momentum",
                stop_loss_price=99.0,
            )
        )
        result = engine.execute_trade(_decision(symbol="AAPL"))
    finally:
        set_config_overrides(None)

    assert result.attempted is False
    assert result.status == "BLOCKED"
    assert result.rationale == "DUPLICATE_POSITION_CONFLICT"
    out = capsys.readouterr().out
    assert "[EXECUTION][SUBMIT]" not in out


def test_no_order_root_cause_summary_logs(capsys) -> None:
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator._emit_execution_root_cause_summary(
        approved_intents_count=2,
        execution_received_count=2,
        submit_attempt_count=0,
        submit_success_count=0,
        dominant_block_reasons={"BROKER_NOT_CONNECTED": 1, "INVALID_ORDER_QUANTITY": 1},
    )

    out = capsys.readouterr().out
    assert "[EXECUTION][NO_ORDER_ROOT_CAUSE]" in out
    assert "approved_intents_count=2" in out
    assert "submit_attempt_count=0" in out


class _ExecutionProviderStub:
    def name(self) -> str:
        return "TEST_EXECUTION_PROVIDER"

    def is_live(self) -> bool:
        return False

    def place_order(self, request):
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=str(request.trader_type or "UNKNOWN"),
            attempted=True,
            status="Filled",
            rationale="stubbed_fill",
            direction=request.direction,
            quantity=request.quantity,
            requested_quantity=request.quantity,
            filled_quantity=request.quantity,
            remaining_quantity=0,
            fill_status="FULL",
            average_fill_price=Decimal("100.00"),
            entry_price=Decimal("100.00"),
            client_order_id=request.client_order_id,
            ibkr_order_id=1001,
        )

    def cancel(self, order_id: str):
        return {"order_id": order_id, "status": "NOT_SUPPORTED", "rationale": "stub"}

    def get_positions(self):
        return PositionSnapshot(positions=[], as_of="2026-04-15T00:00:00+00:00")

    def get_open_orders(self):
        return []

    def place_stop_order(self, **kwargs):
        return {"broker_order_id": "STOP-1", "status": "Submitted"}

    def place_target_order(self, **kwargs):
        return {"broker_order_id": "TGT-1", "status": "Submitted"}

    def modify_stop_order(self, **kwargs):
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, *, broker_order_id: str):
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}


def test_execution_does_not_close_trade() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        provider = _ExecutionProviderStub()
        engine = ExecutionEngine()
        engine._provider = provider
        engine.provider = provider
        engine.post_fill_lifecycle.execution_provider = provider
        long_decision = _decision(symbol="AMD")
        long_result = engine.execute_trade(long_decision)
        assert long_result.status == "Filled"
        trade = engine.post_fill_lifecycle.get_trade(long_result.client_order_id)
        assert trade is not None
        assert trade.state != PositionLifecycleState.EXITED

        short_decision = _decision(symbol="AMD")
        short_decision.direction = "SELL"
        short_result = engine.execute_trade(short_decision)
        assert short_result.status == "Filled"
        assert long_result.client_order_id in engine.post_fill_lifecycle._active_trade_ids
        assert short_result.client_order_id not in engine.post_fill_lifecycle._active_trade_ids
    finally:
        set_config_overrides(None)
