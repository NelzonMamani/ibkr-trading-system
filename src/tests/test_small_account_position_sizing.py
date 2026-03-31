from src.core_engine.events import TradeIntentRecord
from src.core_engine.state import RunMode
from src.risk.risk_audit import INITIAL_POSITION_PCT, AccountSnapshot, evaluate_trade_intents


def test_small_account_uses_full_buying_power() -> None:
    available_funds = 168.0
    focus_count = 1
    entry_price = 10.0
    intents = [
        TradeIntentRecord(
            symbol="ABC",
            intent_id="intent-1",
            setup_id="GAP_GO",
            side="LONG",
            entry="LIMIT",
            stop="STRUCTURE",
            rationale="test",
            entry_price=entry_price,
        )
    ]
    decisions = evaluate_trade_intents(
        intents=intents,
        mode=RunMode.LIVE,
        health_status=None,
        account=AccountSnapshot(
            available_funds=available_funds,
            source="IBKR_CANONICAL",
            canonical=True,
            broker_connection_state="CONNECTED",
        ),
    )
    capital_per_symbol = available_funds / focus_count
    initial_capital = capital_per_symbol * INITIAL_POSITION_PCT
    expected_quantity = int(initial_capital // entry_price)
    assert decisions[0].decision == "ALLOW"
    assert decisions[0].approved_quantity == expected_quantity
    assert decisions[0].risk_allowed is True
