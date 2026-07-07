from scripts.certification import pr1040_real_readonly_runtime_observation_adapter as pr1040
from src.config import runtime_config
from src.core_engine.events import TradeIntentRecord
from src.core_engine.state import RunMode
from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents


def _priced_intent() -> TradeIntentRecord:
    return TradeIntentRecord(
        symbol="REAL1",
        intent_id="REAL1-MICRO_PULLBACK-20260707T120000Z",
        setup_id="MICRO_PULLBACK",
        side="LONG",
        entry="trigger=12.34",
        stop="below recent support",
        rationale="canonical Ross accepted setup with target model entry",
        tags=["ROSS", "REAL_RUNTIME_OBSERVATION"],
        entry_price=12.34,
        entry_price_source="CANONICAL_STRATEGY_ENTRY_MODEL",
        metadata={"decision_authority": pr1040.CANONICAL_DECISION_AUTHORITY},
    )


def test_pr1044_readonly_risk_account_is_bounded_to_adapter_config(monkeypatch) -> None:
    monkeypatch.setattr(runtime_config, "get_risk_account_equity", lambda: 160.0)

    account = pr1040._readonly_risk_account_snapshot()

    assert account.available_funds == 160.0
    assert account.source == "READ_ONLY_CONFIG"
    assert account.canonical is False
    assert account.broker_connection_state == "READ_ONLY_CONFIG"


def test_pr1044_adapter_config_account_allows_priced_readonly_sizing(monkeypatch) -> None:
    monkeypatch.setattr(runtime_config, "get_risk_account_equity", lambda: 160.0)

    decisions = evaluate_trade_intents(
        [_priced_intent()],
        mode=RunMode.READ_ONLY,
        health_status=None,
        account=pr1040._readonly_risk_account_snapshot(),
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.decision == "ALLOW_WITH_CONSTRAINTS"
    assert decision.approved_quantity > 0
    assert decision.available_funds == 160.0
    assert decision.capital_source == "READ_ONLY_CONFIG"
    assert decision.entry_price == 12.34
    assert "MODE_READONLY" in decision.triggered_rules
    assert "READONLY_NO_EXECUTION" in decision.constraints
    assert "INSUFFICIENT_CAPITAL_PER_SYMBOL" not in decision.triggered_rules


def test_pr1044_shared_readonly_zero_account_still_blocks_priced_intent() -> None:
    decisions = evaluate_trade_intents(
        [_priced_intent()],
        mode=RunMode.READ_ONLY,
        health_status=None,
        account=AccountSnapshot(
            available_funds=0.0,
            source="UNAVAILABLE",
            canonical=False,
            broker_connection_state="MISSING",
        ),
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.decision == "BLOCK"
    assert decision.approved_quantity == 0
    assert decision.available_funds == 0.0
    assert decision.capital_source == "UNAVAILABLE"
    assert "MODE_READONLY" in decision.triggered_rules
    assert "INSUFFICIENT_CAPITAL_PER_SYMBOL" in decision.triggered_rules
