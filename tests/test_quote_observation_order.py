"""Synthetic lock/clock schedules, not reconstructions of a natural receipt."""
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from ibapi.client import EClient

from scripts.certification import quote_transport_diagnostic as diagnostic
from src.adapters.brokers.ibkr import ibkr_client as native_module
from src.config.config_resolver import get_config
from src.ibkr import market_data_client as md
from test_post_pr1090_market_data_authority import native, native_ticks, contract, client_for
from test_quote_transport_operator import Fake


class Clock(datetime):
    value = None

    @classmethod
    def now(cls, tz=None):
        return cls.value


@pytest.fixture
def clock(monkeypatch):
    Clock.value = Clock(2026, 1, 5, 12, 0, 0, 997555, tzinfo=timezone.utc)
    for module in (diagnostic, native_module, md):
        monkeypatch.setattr(module, 'datetime', Clock)
    return Clock


class BeforeAcquire:
    """Deterministically schedule one writer before the reader acquires its lock."""
    def __init__(self, lock, action):
        self.lock, self.action = lock, action

    def __enter__(self):
        action, self.action = self.action, None
        if action is not None:
            action()
        self.lock.acquire()
        return self

    def __exit__(self, *args):
        self.lock.release()


def next_tick(clock):
    # Integer-second broker value; local time advances normally, with no skew.
    stamp = Clock(2026, 1, 5, 12, 0, 1, tzinfo=timezone.utc)
    clock.value = stamp + timedelta(microseconds=555)
    return stamp


def test_diagnostic_clock_follows_locked_callback_copy(monkeypatch, clock):
    client = Fake()
    request = client.reqMktData
    def send(*args, **kwargs):
        ticker = request(*args, **kwargs)
        ticker.lastTime = clock.value
        lock = client._lock
        def callback():
            with lock:
                ticker.lastTime = next_tick(clock)
        client._lock = BeforeAcquire(lock, callback)
        return ticker
    client.reqMktData = send
    monkeypatch.setattr('src.core.acquisition.wait_event', lambda event, timeout: True)
    quote = diagnostic.acquire(client, lambda *args: None)['quotes'][0]
    # Old order samples .997555 then copies next-second state: age=-.002445.
    assert quote['age_seconds'] == pytest.approx(.000555)
    assert quote['diagnostic_fields_available']
    assert client.completions == ['snapshot_end'] and not client._market_events


def test_native_completion_clock_follows_locked_callback_copy(native, monkeypatch, clock):
    monkeypatch.setattr(native, 'resolve_contract', lambda symbol: SimpleNamespace(contract=contract()))
    def send(self, req, *args):
        native_ticks(self, req)
        self.tickString(req, 45, str(clock.value.timestamp()))
    monkeypatch.setattr(EClient, 'reqMktData', send)
    original_wait = native_module.wait_event
    def wait(event, timeout):
        result = original_wait(event, timeout)
        req = next(iter(native._ticker_by_req_id))
        def callback():
            native.tickString(req, 45, str(next_tick(clock).timestamp()))
        native._lock = BeforeAcquire(native._lock, callback)
        return result
    monkeypatch.setattr(native_module, 'wait_event', wait)
    result = native.get_market_snapshot('AEMD')
    completed = datetime.fromisoformat(result.request_completed_at_utc)
    received = datetime.fromisoformat(result.field_received_at_utc['market_timestamp'])
    assert completed >= received >= result.market_timestamp_utc
    assert result.snapshot_complete and result.returned_market_data_type == 'LIVE'
    assert not native._market_events and not native._ticker_by_req_id


def test_market_data_client_freezes_state_before_completion_clock(native, monkeypatch, clock):
    def send(self, req, *args):
        native_ticks(self, req)
        self.tickString(req, 45, str(clock.value.timestamp()))
    monkeypatch.setattr(EClient, 'reqMktData', send)
    client = client_for(native)
    read = client._snapshot_debug_fields
    old_stamp = clock.value
    callbacks = []
    def fields(observed):
        req = next(iter(native._ticker_by_req_id))
        callbacks.append(req)
        native.tickPrice(req, 66, 9.0, None)
        native.tickString(req, 45, str(next_tick(clock).timestamp()))
        return read(observed)
    monkeypatch.setattr(client, '_snapshot_debug_fields', fields)
    result = client.snapshot_stock(contract())
    assert len(callbacks) == 1
    assert result.bid == 5.0  # Later callback is not part of the retained view.
    assert datetime.fromisoformat(result.timestamp_utc) == old_stamp
    completed = datetime.fromisoformat(result.request_completed_at_utc)
    assert all(datetime.fromisoformat(t) <= completed for t in result.field_received_at_utc.values())
    assert not native._market_events and not native._ticker_by_req_id


def test_frozen_metadata_does_not_alias_live_ticker_or_copy_sdk_handles(clock):
    ticker = SimpleNamespace(bid=5., lastTime=clock.value,
        fieldReceivedAt={'bid': clock.value.isoformat()}, brokerErrors=[{'code': 1}],
        updateEvent=threading.Lock())
    observed = md._copy_snapshot_ticker(ticker)
    ticker.fieldReceivedAt['bid'] = 'later'
    ticker.brokerErrors[0]['code'] = 2
    ticker.bid = 9.
    assert observed.bid == 5. and observed.lastTime == clock.value
    assert observed.fieldReceivedAt['bid'] == clock.value.isoformat()
    assert observed.brokerErrors == [{'code': 1}]


@pytest.mark.parametrize('case,eligible', [
    ('future', False), ('zero', True), ('boundary', True), ('stale', False),
    ('missing', False), ('local_receipt_only', False),
])
def test_ordered_diagnostic_retains_strict_timestamp_authority(monkeypatch, clock, case, eligible):
    client = Fake()
    request = client.reqMktData
    max_age = int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS'))
    def send(*args, **kwargs):
        ticker = request(*args, **kwargs)
        age = {'future': -.000001, 'zero': 0, 'boundary': max_age,
               'stale': max_age+.000001}.get(case)
        ticker.lastTime = None if age is None else clock.value-timedelta(seconds=age)
        if case == 'local_receipt_only':
            ticker.receivedAt = ticker.time = clock.value
            ticker.timestampSource = 'LOCAL'
        return ticker
    client.reqMktData = send
    monkeypatch.setattr('src.core.acquisition.wait_event', lambda event, timeout: True)
    quote = diagnostic.acquire(client, lambda *args: None)['quotes'][0]
    assert quote['diagnostic_fields_available'] is eligible
    assert quote['canonical_qualification'] == 'NOT_PERFORMED'
    if case in ('missing', 'local_receipt_only'):
        assert quote['market_timestamp_utc'] is None and quote['age_seconds'] is None
    elif case == 'future':
        assert quote['age_seconds'] < 0
    elif case == 'stale':
        assert quote['age_seconds'] > max_age
    assert client.completions == ['snapshot_end'] and not client._market_events


def test_production_observation_preserves_future_broker_timestamp(native, monkeypatch, clock):
    future = clock.value + timedelta(seconds=1)
    def send(self, req, *args):
        native_ticks(self, req)
        self.tickString(req, 45, str(future.timestamp()))
    monkeypatch.setattr(EClient, 'reqMktData', send)
    result = client_for(native).snapshot_stock(contract())
    # Preserve provenance; this is not an assertion of production eligibility.
    assert datetime.fromisoformat(result.timestamp_utc) == future
    assert datetime.fromisoformat(result.timestamp_utc) > datetime.fromisoformat(result.request_completed_at_utc)
