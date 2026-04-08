from types import SimpleNamespace

from src.core_engine.events import RiskDecisionRecord
from src.core_engine.state import RunMode
from src.execution import order_router
from src.execution.e27_lifecycle import ExecutionPlanBuilder, RecoveryEngine, RossExecutionPolicy


def _decision(symbol: str = "E27X") -> RiskDecisionRecord:
    row = RiskDecisionRecord(
        symbol=symbol,
        intent_id=f"{symbol}-1",
        decision="ALLOW",
        max_position_size=10,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        approved_quantity=10,
        entry_price=20.0,
    )
    row.side = "LONG"
    row.strategy_name = "ROSS_MOMENTUM"
    row.stop_loss_price = 19.2
    return row


def test_e27_plan_builder_emits_protection_and_target() -> None:
    builder = ExecutionPlanBuilder()
    plan = builder.build_from_risk_decision(decision=_decision(), policy=RossExecutionPolicy())
    assert isinstance(plan.initial_stop_spec["price"], float)
    assert plan.initial_stop_spec["price"] < 20.0
    assert float(plan.first_target_spec["price"]) > 0.0


def test_execute_intents_logs_e27_plan_and_attachment(monkeypatch, capsys) -> None:
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    out = capsys.readouterr().out
    assert events[0].action == "SUBMITTED"
    assert "[EXECUTION][PLAN_BUILT]" in out
    assert "[EXECUTION][STOP_ATTACHED]" in out
    assert "[EXECUTION][TARGET_ATTACHED]" in out


def test_recovery_engine_flags_orphan_artifacts() -> None:
    engine = RecoveryEngine()
    verdicts = engine.evaluate_broker_truth(
        open_orders=[SimpleNamespace(symbol="ORPHAN_O")],
        positions=[SimpleNamespace(symbol="ORPHAN_P")],
        tracked_order_symbols=set(),
        tracked_position_symbols=set(),
    )
    verdict_kinds = {row.verdict for row in verdicts}
    assert "orphan_order" in verdict_kinds
    assert "orphan_position" in verdict_kinds
