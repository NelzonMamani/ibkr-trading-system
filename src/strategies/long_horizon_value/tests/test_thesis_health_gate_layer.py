from types import SimpleNamespace

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


def test_buy_intent_gets_thesis_fields_healthy() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_thesis_health_gate_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={
            "thesis_health_by_symbol": {
                "AAPL": {"score": 0.82, "status": "HEALTHY", "reasons": ["stable margins"]}
            }
        },
    )

    assert getattr(intents[0], "thesis_health_score") == 0.82
    assert getattr(intents[0], "thesis_health_status") == "HEALTHY"
    assert getattr(intents[0], "thesis_health_reasons") == ["stable margins"]
    assert getattr(intents[0], "thesis_gate_passed") is True


def test_buy_intent_broken_blocks_executable_and_sets_approval_status() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._apply_thesis_health_gate_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={"thesis_health_score_by_symbol": {"AAPL": 0.40}},
    )

    assert getattr(intents[0], "thesis_health_status") == "BROKEN"
    assert getattr(intents[0], "executable") is False
    assert getattr(intents[0], "approval_status") == "THESIS_BROKEN_BLOCK"
    assert any(r.get("status") == "THESIS_BROKEN_BLOCKED_INTENT" for r in reports)


def test_degraded_annotates_but_does_not_block() -> None:
    runner = LongHorizonValueRunner()
    intents, _ = runner._apply_thesis_health_gate_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("ADD")],
        context={"thesis_health_score_by_symbol": {"AAPL": 0.60}},
    )

    assert getattr(intents[0], "thesis_health_status") == "DEGRADED"
    assert getattr(intents[0], "thesis_gate_passed") is False
    assert not hasattr(intents[0], "executable")


def test_unknown_does_not_crash_emits_missing_report_and_does_not_block() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._apply_thesis_health_gate_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context={},
    )

    assert getattr(intents[0], "thesis_health_score") is None
    assert getattr(intents[0], "thesis_health_status") == "UNKNOWN"
    assert getattr(intents[0], "thesis_health_reasons") == []
    assert getattr(intents[0], "thesis_gate_passed") is False
    assert not hasattr(intents[0], "executable")
    assert any(r.get("status") == "THESIS_HEALTH_DATA_MISSING" and r.get("symbol") == "AAPL" for r in reports)


def test_sell_and_trim_untouched_by_thesis_layer() -> None:
    runner = LongHorizonValueRunner()
    sell_intent = _intent("SELL")
    trim_intent = _intent("TRIM")

    intents, _ = runner._apply_thesis_health_gate_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[sell_intent, trim_intent],
        context={"thesis_health_score_by_symbol": {"AAPL": 0.25}},
    )

    assert not hasattr(intents[0], "thesis_health_score")
    assert not hasattr(intents[1], "thesis_health_score")
    assert not hasattr(intents[0], "thesis_gate_passed")
    assert not hasattr(intents[1], "thesis_gate_passed")


def test_attribute_based_context_supported() -> None:
    runner = LongHorizonValueRunner()
    context = SimpleNamespace(thesis_health_score_by_symbol={"AAPL": 0.72})

    intents, _ = runner._apply_thesis_health_gate_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[_intent("BUY")],
        context=context,
    )

    assert getattr(intents[0], "thesis_health_status") == "HEALTHY"


def test_manual_approval_block_not_reenabled_by_thesis_layer() -> None:
    runner = LongHorizonValueRunner()
    blocked = _intent("BUY")
    setattr(blocked, "executable", False)
    setattr(blocked, "approval_status", "PENDING_MANUAL_APPROVAL")

    intents, _ = runner._apply_thesis_health_gate_layer(
        watchlist=[{"symbol": "AAPL"}],
        intents=[blocked],
        context={"thesis_health_score_by_symbol": {"AAPL": 0.82}},
    )

    assert getattr(intents[0], "executable") is False
    assert getattr(intents[0], "approval_status") == "PENDING_MANUAL_APPROVAL"
