from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.execution.execution_engine import ExecutionEngine


def test_is_near_whole_or_half_dollar_levels():
    assert CoreOrchestrator._is_near_whole_or_half_dollar(10.00) is True
    assert CoreOrchestrator._is_near_whole_or_half_dollar(10.49) is True
    assert CoreOrchestrator._is_near_whole_or_half_dollar(10.53) is False


def test_execute_maps_management_intents_to_sell_and_buy(monkeypatch):
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        engine = ExecutionEngine()
    finally:
        set_config_overrides({})

    seen_directions: list[str] = []

    def _capture_execute_trade(risk_decision):
        seen_directions.append(str(getattr(risk_decision, "direction", "")))
        return SimpleNamespace(
            symbol=risk_decision.symbol,
            direction=risk_decision.direction,
            filled_quantity=getattr(risk_decision, "max_position_size", 0),
            status="Submitted",
            attempted=True,
        )

    monkeypatch.setattr(engine, "execute_trade", _capture_execute_trade)

    intents = [
        SimpleNamespace(action="EXIT", symbol="AAPL", quantity=5, reason="RETRACE_FAILURE"),
        SimpleNamespace(action="ADD", symbol="AAPL", quantity=2, reason="GREEN_VOLUME_SCALE"),
    ]
    results = engine.execute(intents)

    assert len(results) == 2
    assert seen_directions == ["SELL", "BUY"]
