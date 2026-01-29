import sys
from importlib.util import find_spec
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

ibkr_available = find_spec("ibapi") is not None

if ibkr_available:
    from adapters.brokers.ibkr.ibkr_order_submitter import (  # noqa: E402
        IbkrOrderSubmitter,
        OrderSubmissionSettings,
    )
    from adapters.brokers.ibkr.submission_guard import SubmissionGuard  # noqa: E402
    from adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator  # noqa: E402
    from config.runtime_config import RunMode  # noqa: E402
    from core.event_collector import EventCollector  # noqa: E402
    from domain.models.internal_order import InternalOrder  # noqa: E402
    from events.event_types import (  # noqa: E402
        ORDER_SUBMISSION_ATTEMPTED,
        ORDER_SUBMISSION_BLOCKED,
        ORDER_SUBMISSION_FAILED,
        ORDER_SUBMITTED_ACK,
    )
else:  # pragma: no cover - executed only when dependency missing
    pytest.skip("ibapi dependency missing; skipping IBKR order submission tests", allow_module_level=True)


class FakeOrderStatus:
    def __init__(self, status: str = "Submitted", order_id: int = 1001):
        self.status = status
        self.orderId = order_id


class FakeTrade:
    def __init__(self, status: FakeOrderStatus):
        self.orderStatus = status


class FakeIbkrClient:
    def __init__(self, raise_on_connect=False, raise_on_place_order=False):
        self.raise_on_connect = raise_on_connect
        self.raise_on_place_order = raise_on_place_order
        self.connected = False
        self.next_order_id = 1001

    def connect(self, *args, **kwargs):
        if self.raise_on_connect:
            raise RuntimeError("Fake connect failure")
        self.connected = True
        return True

    def submit_order(self, contract, order):
        if self.raise_on_place_order:
            raise RuntimeError("Fake submit_order failure")

        order_id = self.next_order_id
        self.next_order_id += 1
        return order_id

    def wait_for_order_status(self, order_id, timeout_seconds=5):
        return {"status": "ACKED"}

    def disconnect(self):
        self.connected = False
    def commission_for_order(self, order_id):
        # Deterministic test value
        return 0.0





def make_settings(
    *,
    run_mode=RunMode.PAPER,
    enabled=True,
    kill_switch=False,
    max_orders=1,
    paper_only=True,
    paper_port=7497,
    live_port=7496,
    submit_only_symbol=None,
    ack_timeout_seconds=1,
):
    return OrderSubmissionSettings(
        run_mode=run_mode,
        order_submission_enabled=enabled,
        kill_switch=kill_switch,
        max_orders_per_run=max_orders,
        paper_only_enforced=paper_only,
        paper_host="127.0.0.1",
        paper_port=paper_port,
        live_port=live_port,
        submit_only_symbol=submit_only_symbol,
        ack_timeout_seconds=ack_timeout_seconds,
        client_id=9012,
        submit_only_order_type="MKT",
        allow_shorting=False,
    )


def make_order(client_order_id: str = "order-1") -> InternalOrder:
    return InternalOrder(
        client_order_id=client_order_id,
        symbol="AAPL",
        direction="LONG",
        quantity=1,
        order_type="MKT",
        limit_price=None,
        time_in_force="DAY",
        strategy_name="TEST",
        trader_type="MANUAL",
    )


def make_submitter(
    settings: OrderSubmissionSettings,
    client: FakeIbkrClient | None = None,
    guard: SubmissionGuard | None = None,
    event_bus: EventCollector | None = None,
):
    client = client or FakeIbkrClient()
    guard = guard or SubmissionGuard(max_orders_per_run=settings.max_orders_per_run, persist_path=None)
    event_bus = event_bus or EventCollector()
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    return IbkrOrderSubmitter(
        ibkr_client=client,
        translator=translator,
        event_bus=event_bus,
        config=settings,
        guard=guard,
    )


def test_submission_blocked_when_kill_switch_true():
    settings = make_settings(kill_switch=True)
    submitter = make_submitter(settings)

    with pytest.raises(RuntimeError, match="Kill-switch enabled"):
        submitter.submit_once(make_order())


def test_submission_blocked_when_run_mode_not_sim():
    settings = make_settings(run_mode=RunMode.SIM)
    submitter = make_submitter(settings)

    # with pytest.raises(RuntimeError, match="RUN_MODE in \\{LIVE, LIVE_MICRO, PAPER\\}"):
    with pytest.raises(
            RuntimeError,
            match=r"RUN_MODE in \{LIVE, LIVE_MICRO, LIVE_ONE_SHARE, PAPER\}"
    ):
        submitter.submit_once(make_order())


def test_submission_blocked_when_disabled():
    settings = make_settings(enabled=False)
    submitter = make_submitter(settings)

    with pytest.raises(RuntimeError, match="disabled by config"):
        submitter.submit_once(make_order())


def test_submission_blocks_second_order_same_run():
    settings = make_settings()
    guard = SubmissionGuard(max_orders_per_run=1, persist_path=None)
    event_bus = EventCollector()
    submitter = make_submitter(settings, guard=guard, event_bus=event_bus)

    first_result = submitter.submit_once(make_order("order-1"))
    assert first_result.status == "ACKED"

    second_result = submitter.submit_once(make_order("order-2"))
    assert second_result.status == "BLOCKED"
    assert guard.submitted_count() == 1
    assert event_bus.count(ORDER_SUBMISSION_BLOCKED) == 1


def test_idempotency_blocks_same_client_order_id_twice():
    settings = make_settings(max_orders=2)
    guard = SubmissionGuard(max_orders_per_run=2, persist_path=None)
    event_bus = EventCollector()
    submitter = make_submitter(settings, guard=guard, event_bus=event_bus)

    first_result = submitter.submit_once(make_order("dup-order"))
    assert first_result.status == "ACKED"
    second_result = submitter.submit_once(make_order("dup-order"))

    assert second_result.status == "BLOCKED"
    assert guard.submitted_count() == 1
    assert event_bus.count(ORDER_SUBMISSION_BLOCKED) == 1


def test_success_path_marks_submitted_and_emits_events():
    settings = make_settings()
    event_bus = EventCollector()
    guard = SubmissionGuard(max_orders_per_run=1, persist_path=None)
    submitter = make_submitter(settings, guard=guard, event_bus=event_bus)

    result = submitter.submit_once(make_order("success-order"))

    assert result.status == "ACKED"
    assert guard.submitted_count() == 1
    assert event_bus.count(ORDER_SUBMISSION_ATTEMPTED) == 1
    assert event_bus.count(ORDER_SUBMITTED_ACK) == 1
    assert result.ibkr_order_id == 1001


def test_placeOrder_exception_does_not_mark_submitted():
    settings = make_settings()
    guard = SubmissionGuard(max_orders_per_run=1, persist_path=None)
    event_bus = EventCollector()
    client = FakeIbkrClient(raise_on_place_order=True)
    submitter = make_submitter(settings, client=client, guard=guard, event_bus=event_bus)

    result = submitter.submit_once(make_order("fail-order"))

    assert result.status == "FAILED"
    assert guard.submitted_count() == 0
    assert event_bus.count(ORDER_SUBMISSION_FAILED) == 1
