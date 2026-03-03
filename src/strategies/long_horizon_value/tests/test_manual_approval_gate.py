from src.config.runtime_config import RunMode
from src.models.data_models import TradeIntent
from src.strategies.long_horizon_value.runner import LongHorizonValueRunner


def _intent(direction: str = "LONG") -> TradeIntent:
    return TradeIntent(
        symbol="AAPL",
        direction=direction,
        strategy_name="LongHorizonValue",
        confidence=0.6,
        rationale="test",
    )


def test_buy_without_approval_is_blocked() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._enforce_manual_approval_gate(
        intents=[_intent("LONG")],
        context={"manual_approval": False},
        mode=RunMode.SIM,
    )

    assert len(intents) == 1
    assert getattr(intents[0], "executable") is False
    assert getattr(intents[0], "approval_status") == "PENDING_MANUAL_APPROVAL"
    assert any(r.get("status") == "MANUAL_APPROVAL_REQUIRED" and r.get("action") == "BUY" for r in reports)


def test_buy_with_approval_is_allowed() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._enforce_manual_approval_gate(
        intents=[_intent("LONG")],
        context={"manual_approval": True},
        mode=RunMode.SIM,
    )

    assert len(intents) == 1
    assert not hasattr(intents[0], "executable")
    assert not hasattr(intents[0], "approval_status")
    assert not any(r.get("status") == "MANUAL_APPROVAL_REQUIRED" for r in reports)


def test_read_only_always_blocked_even_with_approval() -> None:
    runner = LongHorizonValueRunner()
    intents, reports = runner._enforce_manual_approval_gate(
        intents=[_intent("LONG")],
        context={"manual_approval": True},
        mode=RunMode.READ_ONLY,
    )

    assert len(intents) == 1
    assert getattr(intents[0], "executable") is False
    assert getattr(intents[0], "approval_status") == "PENDING_MANUAL_APPROVAL"
    statuses = [r.get("status") for r in reports]
    assert "READ_ONLY_BLOCK" in statuses
    assert "MANUAL_APPROVAL_REQUIRED" in statuses


def test_sell_and_trim_not_blocked_by_manual_approval_rule() -> None:
    runner = LongHorizonValueRunner()
    sell = _intent("SHORT")
    setattr(sell, "action", "SELL")
    trim = _intent("LONG")
    setattr(trim, "action", "TRIM")

    intents, reports = runner._enforce_manual_approval_gate(
        intents=[sell, trim],
        context={"manual_approval": False},
        mode=RunMode.LIVE,
    )

    assert len(intents) == 2
    assert all(not hasattr(intent, "approval_status") for intent in intents)
    assert all(not hasattr(intent, "executable") for intent in intents)
    assert not any(r.get("status") == "MANUAL_APPROVAL_REQUIRED" for r in reports)
