from importlib.util import find_spec
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

ibkr_available = find_spec("ibapi") is not None

if ibkr_available:
    from adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator  # noqa: E402
    from domain.models.internal_order import InternalOrder  # noqa: E402
else:  # pragma: no cover - executed only when dependency missing
    IbkrOrderTranslator = None  # type: ignore[assignment]
    InternalOrder = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    not ibkr_available,
    reason="ibapi dependency missing; skipping IBKR order translation tests",
)


def test_long_market_translation(capsys):
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="test-1",
        symbol="AAPL",
        direction="LONG",
        quantity=10,
        order_type="MKT",
        time_in_force="DAY",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    contract, order = translator.translate(internal_order)

    assert contract.symbol == "AAPL"
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"
    assert contract.secType == "STK"
    assert order.action == "BUY"
    assert order.orderType == "MKT"
    assert order.totalQuantity == 10
    assert order.tif == "DAY"
    assert order.outsideRth is True

    captured = capsys.readouterr().out
    assert "[IBKR][ORDER_TRANSLATION] Translated Order:" in captured
    assert "outsideRth=True" in captured


def test_long_translation_defaults_missing_fields_to_valid_values():
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="defaults-1",
        symbol="AAPL",
        direction="BUY",
        quantity=3,
        order_type="",
        time_in_force="",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    contract, order = translator.translate(internal_order)

    assert contract.symbol == "AAPL"
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"
    assert contract.secType == "STK"
    assert order.action == "BUY"
    assert order.orderType == "MKT"
    assert order.tif == "DAY"
    assert order.totalQuantity == 3


def test_short_limit_translation():
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="test-2",
        symbol="MSFT",
        direction="SHORT",
        quantity=5,
        order_type="LMT",
        limit_price=310.5,
        time_in_force="IOC",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    contract, order = translator.translate(internal_order)

    assert contract.symbol == "MSFT"
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"
    assert order.action == "SELL"
    assert order.orderType == "LMT"
    assert order.lmtPrice == 310.5
    assert order.tif == "IOC"
    assert order.outsideRth is True


def test_sell_translation_maps_to_sell_action():
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="test-sell",
        symbol="MSFT",
        direction="SELL",
        quantity=2,
        order_type="MKT",
        time_in_force="DAY",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    _, order = translator.translate(internal_order)
    assert order.action == "SELL"


def test_invalid_direction_raises():
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="invalid-direction",
        symbol="AAPL",
        direction="SIDEWAYS",
        quantity=1,
        order_type="MKT",
        time_in_force="DAY",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    with pytest.raises(ValueError, match="INVALID_DIRECTION"):
        translator.translate(internal_order)


def test_missing_limit_price_falls_back_to_market_order():
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="missing-limit",
        symbol="AAPL",
        direction="LONG",
        quantity=1,
        order_type="LMT",
        time_in_force="DAY",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    _, order = translator.translate(internal_order)
    assert order.orderType == "MKT"
    assert getattr(order, "lmtPrice", None) is None


def test_limit_order_with_invalid_limit_price_falls_back_to_market_order():
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="bad-limit",
        symbol="AAPL",
        direction="LONG",
        quantity=1,
        order_type="LIMIT",
        limit_price=-1,
        time_in_force="DAY",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    _, order = translator.translate(internal_order)
    assert order.orderType == "MKT"


def test_non_positive_quantity_is_still_mapped_deterministically():
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id="qty-zero",
        symbol="AAPL",
        direction="LONG",
        quantity=0,
        order_type="MKT",
        time_in_force="DAY",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    _, order = translator.translate(internal_order)
    assert order.totalQuantity == 0


def test_translation_disabled_by_config():
    translator = IbkrOrderTranslator(order_translation_enabled=False)
    internal_order = InternalOrder(
        client_order_id="disabled",
        symbol="AAPL",
        direction="LONG",
        quantity=1,
        order_type="MKT",
        time_in_force="DAY",
        strategy_name="UNIT_TEST",
        trader_type="MANUAL",
    )

    with pytest.raises(RuntimeError, match="translation disabled"):
        translator.translate(internal_order)
