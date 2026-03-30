from __future__ import annotations

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTrade
from src.core.orchestrator import CoreOrchestrator
from src.execution.execution_engine import ExecutionEngine
from src.models.data_models import RiskDecision


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
