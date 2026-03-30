from src.core_engine.events import RiskDecisionRecord, TradeIntentRecord
from src.core_engine.state import RunMode
from src.execution.order_router import execute_intents
from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents


def _intent(symbol: str, price: float = 2.5) -> TradeIntentRecord:
    return TradeIntentRecord(
        symbol=symbol,
        intent_id=f"{symbol}-1",
        setup_id="Micro Pullback",
        side="LONG",
        entry="Breakout",
        stop="Below support",
        rationale="test",
        tags=[],
        entry_price=price,
    )


def test_risk_allow_decision_has_non_zero_approved_quantity() -> None:
    decisions = evaluate_trade_intents(
        intents=[_intent("POLA", price=2.0)],
        mode=RunMode.LIVE,
        health_status=None,
        account=AccountSnapshot(
            available_funds=100.0,
            source="IBKR_CANONICAL",
            canonical=True,
            broker_connection_state="CONNECTED",
        ),
    )

    assert decisions[0].decision == "ALLOW"
    assert decisions[0].approved_quantity > 0


def test_execution_rejects_allow_with_zero_quantity() -> None:
    decision = RiskDecisionRecord(
        symbol="POLA",
        intent_id="POLA-1",
        decision="ALLOW",
        max_position_size=1,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        capital_source="IBKR_CANONICAL",
        approved_quantity=0,
    )

    try:
        execute_intents(mode=RunMode.LIVE, decisions=[decision])
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "INVALID ORDER: quantity=0" in str(exc)

    assert raised
