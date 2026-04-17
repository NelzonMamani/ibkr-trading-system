from __future__ import annotations

from types import SimpleNamespace

from src.execution.fill_diagnostics import (
    FillabilityClass,
    NormalizedInactiveReason,
    classify_fillability,
    normalize_inactive_reason,
)


def _order(action: str, order_type: str, lmt: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(action=action, orderType=order_type, lmtPrice=lmt)


def test_buy_market_is_marketable_buy() -> None:
    result = classify_fillability(_order("BUY", "MKT"), {"bid": 10.0, "ask": 10.1})
    assert result == FillabilityClass.MARKETABLE_BUY


def test_buy_limit_above_ask_is_crossing_aggressive() -> None:
    result = classify_fillability(_order("BUY", "LMT", 10.2), {"bid": 10.0, "ask": 10.1})
    assert result == FillabilityClass.CROSSING_AGGRESSIVE


def test_buy_limit_inside_spread_is_inside_spread() -> None:
    result = classify_fillability(_order("BUY", "LMT", 10.05), {"bid": 10.0, "ask": 10.1})
    assert result == FillabilityClass.INSIDE_SPREAD


def test_buy_limit_below_bid_is_passive() -> None:
    result = classify_fillability(_order("BUY", "LMT", 9.9), {"bid": 10.0, "ask": 10.1})
    assert result == FillabilityClass.PASSIVE


def test_missing_quote_is_no_quote() -> None:
    result = classify_fillability(_order("BUY", "LMT", 10.1), {"bid": None, "ask": 10.1})
    assert result == FillabilityClass.NO_QUOTE


def test_inactive_crossing_buy_classifies_routing_or_unknown() -> None:
    reason = normalize_inactive_reason(
        _order("BUY", "LMT", 10.2),
        SimpleNamespace(status="Inactive", whyHeld=""),
        {"bid": 10.0, "ask": 10.1},
    )
    assert reason in {NormalizedInactiveReason.ROUTING, NormalizedInactiveReason.UNKNOWN}


def test_inactive_with_no_quote_classifies_no_quote() -> None:
    reason = normalize_inactive_reason(
        _order("BUY", "LMT", 10.2),
        SimpleNamespace(status="Inactive", whyHeld=""),
        {"bid": None, "ask": None},
    )
    assert reason == NormalizedInactiveReason.NO_QUOTE
