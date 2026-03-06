from src.core_engine.events import TradeIntentRecord
from src.core_engine.state import RunMode
from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents


def test_small_account_uses_full_buying_power() -> None:
    intents = [
        TradeIntentRecord(
            symbol="ABC",
            intent_id="intent-1",
            setup_id="GAP_GO",
            side="LONG",
            entry="LIMIT",
            stop="STRUCTURE",
            rationale="test",
            entry_price=10.0,
        )
    ]
    decisions = evaluate_trade_intents(
        intents=intents,
        mode=RunMode.LIVE,
        health_status=None,
        account=AccountSnapshot(available_funds=168.0),
    )
    assert decisions[0].decision == "ALLOW"
    assert decisions[0].max_position_size == 16
    assert decisions[0].risk_allowed is True
