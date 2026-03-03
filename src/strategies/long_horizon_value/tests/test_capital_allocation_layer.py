from src.models.data_models import TradeIntent
from src.strategies.long_horizon_value.runner import LongHorizonValueRunner


def _intent(action: str = "BUY") -> TradeIntent:
    intent = TradeIntent(
        symbol="AAPL",
        direction="LONG",
        strategy_name="LongHorizonValue",
        confidence=0.7,
        rationale="test",
    )
    setattr(intent, "action", action)
    return intent


def test_default_tier_applied_when_missing() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._apply_capital_allocation_layer(intents=[_intent("BUY")], context={})

    assert getattr(intents[0], "conviction_tier") == "C"
    assert any(report.get("status") == "CAPITAL_ALLOCATION_SNAPSHOT" for report in reports)


def test_tier_weight_respected() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_capital_allocation_layer(
        intents=[_intent("BUY")],
        context={"conviction_tier": "B"},
    )

    assert getattr(intents[0], "target_weight") == 0.05


def test_max_position_clamp_works() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_capital_allocation_layer(
        intents=[_intent("BUY")],
        context={"conviction_tier": "A"},
    )

    assert getattr(intents[0], "target_weight") == 0.08


def test_first_entry_uses_half_target_weight() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_capital_allocation_layer(
        intents=[_intent("BUY")],
        context={"conviction_tier": "B", "existing_position_weight": 0.0},
    )

    assert getattr(intents[0], "proposed_tranche_weight") == 0.025


def test_add_uses_remaining_portion_split_across_three_tranches() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_capital_allocation_layer(
        intents=[_intent("ADD")],
        context={"conviction_tier": "A", "existing_position_weight": 0.02},
    )

    assert getattr(intents[0], "target_weight") == 0.08
    assert getattr(intents[0], "proposed_tranche_weight") == 0.02


def test_sell_and_trim_untouched() -> None:
    runner = LongHorizonValueRunner()
    sell_intent = _intent("SELL")
    trim_intent = _intent("TRIM")

    intents, reports = runner._apply_capital_allocation_layer(
        intents=[sell_intent, trim_intent],
        context={"conviction_tier": "A", "existing_position_weight": 0.01},
    )

    assert len(intents) == 2
    assert not hasattr(intents[0], "target_weight")
    assert not hasattr(intents[1], "target_weight")
    assert reports == []
