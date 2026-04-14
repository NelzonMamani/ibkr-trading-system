from __future__ import annotations

from src.execution import order_router


def test_fillability_buy_sell_limit_against_bid_ask() -> None:
    buy_classification, _ = order_router.classify_submit_fillability(
        order_type="LMT",
        action="BUY",
        lmt_price=10.01,
        bid=9.95,
        ask=10.0,
    )
    sell_classification, _ = order_router.classify_submit_fillability(
        order_type="LMT",
        action="SELL",
        lmt_price=9.95,
        bid=10.0,
        ask=10.05,
    )
    passive_classification, _ = order_router.classify_submit_fillability(
        order_type="LMT",
        action="BUY",
        lmt_price=9.8,
        bid=9.95,
        ask=10.0,
    )

    assert buy_classification == "CROSSING_ASK_AGGRESSIVE"
    assert sell_classification == "CROSSING_BID_AGGRESSIVE"
    assert passive_classification == "PASSIVE_AWAY_FROM_MARKET"


def test_inactive_normalization_by_session_outside_rth_and_passive_limit() -> None:
    reason, rationale = order_router.normalize_inactive_reason(
        submit_payload={
            "outside_rth": False,
            "tif": "DAY",
            "session_label": "PRE",
            "exchange": "SMART",
            "bid": 10.0,
            "ask": 10.1,
        },
        open_order_echo={"outside_rth": False, "tif": "DAY"},
        broker_status="INACTIVE",
        why_held="",
        session_label="PRE",
        fillability="PASSIVE_AWAY_FROM_MARKET",
        quote_available=True,
    )
    assert reason == "SESSION_MISMATCH"
    assert "outside_rth" in rationale or "session" in rationale.lower()


def test_inactive_normalization_no_quote_and_whyheld_priority() -> None:
    held_reason, _ = order_router.normalize_inactive_reason(
        submit_payload={"outside_rth": True, "tif": "DAY"},
        open_order_echo={},
        broker_status="INACTIVE",
        why_held="held by broker risk",
        session_label="RTH",
        fillability="MARKETABLE_BUY_AT_OR_ABOVE_ASK",
        quote_available=True,
    )
    no_quote_reason, _ = order_router.normalize_inactive_reason(
        submit_payload={"outside_rth": True, "tif": "DAY"},
        open_order_echo={},
        broker_status="INACTIVE",
        why_held="",
        session_label="RTH",
        fillability="NO_QUOTE_CONTEXT",
        quote_available=False,
    )

    assert held_reason == "ROUTING_REJECT"
    assert no_quote_reason == "NO_LIQUIDITY"


def test_authoritative_state_still_prefers_exec_fill_truth() -> None:
    row = order_router.TrackedOrder(
        broker_order_id=77,
        order_ref="ref",
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        filled_qty=10,
        remaining_qty=0,
    )
    row.fill_seen = True
    row.inactive_seen = True
    row.inactive_normalized_reason = "NON_MARKETABLE"

    assert order_router._resolve_authoritative_execution_state(row) == "BROKER_FILLED_FULL"
