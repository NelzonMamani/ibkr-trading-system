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


def test_equal_weighted_intrinsic_when_weights_missing() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._apply_valuation_scenario_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={
            "price_by_symbol": {"AAPL": 100.0},
            "intrinsic_value_by_symbol": {"AAPL": {"base": 130.0, "bear": 90.0, "bull": 170.0}},
        },
    )

    assert getattr(intents[0], "valuation_weighted_intrinsic") == 130.0
    assert any(r.get("status") == "VALUATION_SCENARIO_SNAPSHOT" for r in reports)


def test_computes_mos_when_price_present() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_valuation_scenario_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={
            "price_by_symbol": {"AAPL": 100.0},
            "intrinsic_value_by_symbol": {"AAPL": {"BASE": 130.0, "BEAR": 90.0, "BULL": 170.0}},
            "scenario_weights": {"BASE": 0.5, "BEAR": 0.25, "BULL": 0.25},
        },
    )

    assert getattr(intents[0], "valuation_mos") == 0.3


def test_buy_gate_passed_threshold() -> None:
    runner = LongHorizonValueRunner()
    high_mos_intents, _ = runner._apply_valuation_scenario_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={
            "price_by_symbol": {"AAPL": 100.0},
            "intrinsic_value_by_symbol": {"AAPL": {"BASE": 120.0, "BEAR": 120.0, "BULL": 120.0}},
        },
    )
    low_mos_intents, _ = runner._apply_valuation_scenario_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={
            "price_by_symbol": {"AAPL": 100.0},
            "intrinsic_value_by_symbol": {"AAPL": {"BASE": 104.0, "BEAR": 104.0, "BULL": 104.0}},
        },
    )

    assert getattr(high_mos_intents[0], "buy_gate_passed") is True
    assert getattr(low_mos_intents[0], "buy_gate_passed") is False


def test_missing_intrinsic_data_emits_report_without_crash() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._apply_valuation_scenario_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={"price_by_symbol": {"AAPL": 100.0}},
    )

    assert len(intents) == 1
    assert not hasattr(intents[0], "buy_gate_passed")
    assert any(r.get("status") == "VALUATION_DATA_MISSING" and r.get("symbol") == "AAPL" for r in reports)


def test_buy_intent_gets_valuation_fields() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_valuation_scenario_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={
            "last_price_by_symbol": {"AAPL": 100.0},
            "intrinsic_value_by_symbol": {"AAPL": {"BASE": 120.0, "BEAR": 110.0, "BULL": 130.0}},
        },
    )

    assert hasattr(intents[0], "valuation_weighted_intrinsic")
    assert hasattr(intents[0], "valuation_mos")
    assert hasattr(intents[0], "valuation_band")
    assert hasattr(intents[0], "valuation_scenarios")


def test_sell_and_trim_do_not_get_valuation_fields() -> None:
    runner = LongHorizonValueRunner()
    sell_intent = _intent("SELL")
    trim_intent = _intent("TRIM")

    intents, reports = runner._apply_valuation_scenario_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[sell_intent, trim_intent],
        context={
            "price_by_symbol": {"AAPL": 100.0},
            "intrinsic_value_by_symbol": {"AAPL": {"BASE": 120.0, "BEAR": 110.0, "BULL": 130.0}},
        },
    )

    assert len(intents) == 2
    assert not hasattr(intents[0], "valuation_weighted_intrinsic")
    assert not hasattr(intents[1], "valuation_weighted_intrinsic")
    assert any(r.get("status") == "VALUATION_SCENARIO_SNAPSHOT" for r in reports)
