"""Capture-only history owner: actual native SDK encoding, synthetic callbacks.

No connection, provider, broker or observer acquisition is permitted here.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient

from test_history_completion_ownership import (
    owner, contract, retired, prohibit_acquisition_and_mutation,
)
from test_next_session_catalyst import receipt
from src.adapters.brokers.ibkr import ibkr_client as native
from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionConfig, IbkrConnectionManager
from src.adapters.data import historical_data_provider as provider
from src.config import config_resolver as cfg
from src.ibkr.market_data_client import HistoricalDataResult
from src.market_data.candidate_identity import CandidateIdentity


SDK_HISTORY_ENCODER = EClient.reqHistoricalData
# Pattern fixtures copy their temporary override into this shared module while
# building runtime inputs. Capture the real owner before any fixture runs.
CANONICAL_INTRADAY_PROVIDER = provider.get_intraday_bars
UTC = timezone.utc
OPEN = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)


@pytest.fixture
def capture(owner, monkeypatch):
    provider.get_intraday_bars = CANONICAL_INTRADAY_PROVIDER
    for name in ('FORCE_SESSION', 'SESSION_OVERRIDE', 'MARKET_SESSION_OVERRIDE'):
        monkeypatch.delenv(name, raising=False)
    cfg.set_config_overrides(dict(MARKET_SESSION_COVERAGE=json.dumps(receipt('2026-11-12', '2026-11-13')),
        MARKET_HOLIDAYS=set(), MARKET_HALF_DAYS=set(), SESSION_PHASE_OVERRIDE=None))
    class Clock(datetime):
        current = OPEN + timedelta(minutes=16, seconds=29)
        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else cls.current.astimezone(tz)
    monkeypatch.setattr(provider, 'datetime', Clock)
    monkeypatch.setattr(native, 'datetime', Clock)
    c = owner.client
    # Existing native request fixture supplies the connected, memory-only SDK
    # boundary. These are its explicit synthetic handshake identity facts.
    c.client_id = c.clientId = 71
    manager = IbkrConnectionManager(IbkrConnectionConfig('127.0.0.1', 7497, 71, 5, 'LIVE', True))
    manager._client = c
    monkeypatch.setattr(provider, 'get_shared_ibkr_connection_manager', lambda **kw: manager)
    def forbidden(*args, **kwargs):
        pytest.fail('Bound history must not resolve, connect or repair a source')
    for name in ('get_client', 'ensure_connected', 'connect'):
        monkeypatch.setattr(manager, name, forbidden)
    monkeypatch.setattr(c, 'resolve_contract', forbidden)
    monkeypatch.setattr(c, 'serverVersion', lambda: 180)
    monkeypatch.setattr(EClient, 'reqHistoricalData', SDK_HISTORY_ENCODER)
    values = [NS(date=str(int((OPEN + timedelta(minutes=i)).timestamp())),
        open=10., high=10.2, low=9.9, close=10.1, volume=1000) for i in range(16)]
    packets = []
    state = NS(owner=owner, client=c, manager=manager, clock=Clock, bars=values,
        packets=packets, finish=True, after_callbacks=None, contract=contract())
    def wire(message):
        fields = message.split('\0')
        assert fields[0] == '20', 'Only the actual history read encoder is allowed'
        packets.append(fields)
        req = int(fields[1]); owner.sent.append(req)
        for bar in state.bars:
            c.historicalData(req, bar)
        if state.finish:
            c.historicalDataEnd(req, 'original-sdk-start', 'original-sdk-end')
        if state.after_callbacks:
            state.after_callbacks()
    monkeypatch.setattr(c, 'sendMsg', wire)
    state.call = lambda **changes: provider.get_intraday_bars(**dict(dict(symbol='SYNTH',
        completed_opening=True, expected_client=c, expected_connection_epoch=0,
        qualified_contract=state.contract, expected_identity=CandidateIdentity.from_contract(state.contract)), **changes))
    try:
        yield state
    finally:
        provider.get_intraday_bars = CANONICAL_INTRADAY_PROVIDER
        retired(c)
        cfg.set_config_overrides(None)


def test_fixture_uses_actual_provider_after_foreign_alias_copy(request):
    called = []
    def foreign_history(*, symbol, timeframe='1m', limit=50):
        called.append(symbol)
        pytest.fail('A copied pattern fixture must not replace the provider owner')
    # Reproduce the shared-module assignment made by build_runtime_pattern_inputs
    # before requesting this fixture, without inventing any history result.
    provider.get_intraday_bars = foreign_history
    try:
        captured = request.getfixturevalue('capture')
        result = captured.call()
        assert provider.get_intraday_bars is CANONICAL_INTRADAY_PROVIDER
        assert result.completed and len(captured.packets) == 1 and called == []
        assert result.request_spec.end_date_time == '20261113-14:46:00'
    finally:
        provider.get_intraday_bars = CANONICAL_INTRADAY_PROVIDER


@pytest.mark.parametrize('field,value', [('client_id', 72), ('clientId', 72),
    ('client_id', True), ('clientId', True), ('_position_connection_epoch', False)])
def test_bound_owner_rejects_wrong_or_noninteger_actual_identity_without_send(capture, field, value):
    setattr(capture.client, field, value)
    result = capture.call()
    assert not result.completed and not capture.packets
    assert result.request_spec is None and result.request_dispatched_at_utc is None


def test_postdispatch_normalization_exception_retains_original_source(capture, monkeypatch):
    def broken(*args, **kwargs):
        raise AttributeError('synthetic normalizer defect after owned source completion')
    monkeypatch.setattr(provider, '_normalize_intraday_history', broken)
    result = capture.call()
    assert result.status == 'COMPLETED_OPENING_SOURCE_ERROR'
    assert len(capture.packets) == 1 and result.end_received
    assert result.request_id == capture.owner.sent[0]
    assert result.source_bar_count == len(result.raw_source_bars) == 16
    assert result.request_spec.end_date_time == '20261113-14:46:00'
    assert result.request_dispatched_at_utc == result.completed_at_utc == capture.clock.current.isoformat()


def test_actual_native_encoder_uses_completed_opening_and_original_source_frame(capture):
    result = capture.call()
    fields = capture.packets[0]
    assert result.completed and len(result) == 16
    assert fields[2:5] == ['123', 'SYNTH', 'STK'] and fields[11] == 'USD'
    assert fields[15:23] == ['20261113-14:46:00', '1 min', '960 S', '1', 'TRADES', '2', '0', '']
    assert result.request_spec.timestamp_semantics == 'UTC_BAR_START'
    assert result.contract_identity == result.dispatched_contract_identity == CandidateIdentity.from_contract(capture.contract)
    assert result.callback_start == 'original-sdk-start' and result.callback_end == 'original-sdk-end'
    assert result.request_dispatched_at_utc == result.completed_at_utc == capture.clock.current.isoformat()
    assert result.raw_bar_timestamps == result.normalized_raw_bar_timestamps
    assert result.source_bar_count == result.normalization_selected_count == 16
    assert result.normalization_rejected_count == 0 and capture.owner.cancel == []


def test_ordinary_default_still_uses_existing_window_and_suffix(capture, monkeypatch):
    monkeypatch.setattr(capture.manager, 'get_client', lambda: capture.client)
    monkeypatch.setattr(capture.client, 'resolve_contract', lambda symbol: capture.contract)
    result = provider.get_intraday_bars(symbol='SYNTH', limit=2)
    assert result.completed and len(result) == 2
    assert capture.packets[0][15:23] == ['', '1 min', '1800 S', '0', 'TRADES', '2', '0', '']
    assert result.normalization_selected_count == 2 and result.source_bar_count == 16
    assert result[0].timestamp == OPEN + timedelta(minutes=14)


def test_all_59_source_rows_are_retained_without_sort_or_limit_crop(capture):
    capture.clock.current = OPEN + timedelta(minutes=59, seconds=29)
    capture.bars[:] = [replace_bar(capture.bars[0], date=str(int((OPEN + timedelta(minutes=i)).timestamp())))
        for i in range(59)]
    capture.bars[3], capture.bars[4] = capture.bars[4], capture.bars[3]
    result = capture.call()
    assert result.completed and len(result) == result.normalization_selected_count == 59
    assert capture.packets[0][15:18] == ['20261113-15:29:00', '1 min', '3540 S']
    assert result.raw_bar_timestamps == tuple(bar.date for bar in capture.bars)
    assert result.normalized_raw_bar_timestamps == result.raw_bar_timestamps
    assert len(result.raw_source_bars) == len(result.normalization_source_bars) == 59


def replace_bar(bar, **changes):
    return NS(**dict(vars(bar), **changes))


@pytest.mark.parametrize('kind', ['forming', 'gap', 'malformed', 'boolean', 'missing_volume'])
def test_unfavorable_returned_facts_are_retained_not_repaired(capture, kind):
    if kind == 'forming':
        capture.bars.append(replace_bar(capture.bars[0], date=str(int((OPEN + timedelta(minutes=16)).timestamp()))))
    elif kind == 'gap':
        capture.bars[3] = replace_bar(capture.bars[3], date=str(int((OPEN + timedelta(minutes=30)).timestamp())))
    elif kind == 'malformed':
        capture.bars[3].close = 'not-a-price'
    elif kind == 'boolean':
        capture.bars[3].volume = True
    else:
        del capture.bars[3].volume
    result = capture.call()
    rejected = int(kind in {'malformed', 'boolean', 'missing_volume'})
    assert result.completed and result.normalization_rejected_count == rejected
    assert result.normalization_selected_count == result.source_bar_count == len(capture.bars)
    assert len(result) == len(capture.bars) - rejected
    assert result.raw_source_bars == result.normalization_source_bars
    assert result.raw_bar_timestamps == tuple(bar.date for bar in capture.bars)


@pytest.mark.parametrize('kind', ['early', 'closed', 'override', 'missing_calendar', 'timeframe',
    'identity', 'contract', 'readonly', 'disconnected', 'stopped', 'other_client'])
def test_refused_plan_has_no_fabricated_wire_spec_or_completion(capture, monkeypatch, kind):
    changes = {}
    if kind == 'early': capture.clock.current = OPEN + timedelta(minutes=15, seconds=59)
    elif kind == 'closed': capture.clock.current = OPEN + timedelta(hours=1)
    elif kind == 'override': monkeypatch.setenv('FORCE_SESSION', 'RTH_OPEN')
    elif kind == 'missing_calendar': cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, MARKET_SESSION_COVERAGE=None))
    elif kind == 'timeframe': changes['timeframe'] = '5m'
    elif kind == 'identity': changes['expected_identity'] = replace(CandidateIdentity.from_contract(capture.contract), con_id=999)
    elif kind == 'contract': changes['qualified_contract'] = NS(**vars(capture.contract))
    elif kind == 'readonly': capture.client.readonly_enabled = False
    elif kind == 'disconnected': monkeypatch.setattr(capture.client, 'isConnected', lambda: False)
    elif kind == 'stopped': capture.client._stop_event.set()
    else: capture.manager._client = None
    result = capture.call(**changes)
    assert not result.completed and not capture.packets
    assert result.request_spec is None and result.request_id is None
    assert result.request_dispatched_at_utc is None and result.completed_at_utc is None


@pytest.mark.parametrize('kind', ['epoch', 'owner', 'late', 'calendar'])
def test_postdispatch_source_change_preserves_original_raw_witness(capture, kind):
    def change():
        if kind == 'epoch': capture.client._position_connection_epoch += 1
        elif kind == 'owner': capture.manager._client = None
        elif kind == 'late': capture.clock.current = OPEN + timedelta(hours=1)
        else: cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, MARKET_SESSION_COVERAGE=None))
    capture.after_callbacks = change
    result = capture.call()
    assert not result.completed and result.end_received and len(capture.packets) == 1
    assert result.request_spec is not None and result.request_dispatched_at_utc is not None
    assert result.completed_at_utc is not None and result.source_bar_count == 16
    assert len(result.raw_source_bars) == 16 and result.bars == ()


def test_partial_timeout_keeps_raw_rows_without_promoting_completion(capture):
    capture.finish = False
    result = capture.call()
    assert result.status == 'TIMEOUT' and not result.completed and result.bars == ()
    assert result.partial_count == result.source_bar_count == len(result.raw_source_bars) == 16
    assert result.request_spec is not None and result.request_dispatched_at_utc is not None
    assert capture.owner.cancel == capture.owner.sent
    capture.client.historicalDataEnd(result.request_id, 'late', 'late')
    retired(capture.client)
    assert not result.completed


@pytest.mark.parametrize('field', ['contract_identity', 'dispatched_contract_identity', 'request_spec',
    'request_id', 'request_dispatched_at_utc', 'completed_at_utc', 'callback_start', 'callback_end',
    'source_bar_count', 'raw_source_bars'])
def test_missing_actual_source_witness_is_never_filled_in(capture, monkeypatch, field):
    original = capture.client.reqHistoricalData
    def missing(*args, **kwargs):
        return replace(original(*args, **kwargs), **{field: None})
    monkeypatch.setattr(capture.client, 'reqHistoricalData', missing)
    result = capture.call()
    assert result.status == 'COMPLETED_OPENING_SOURCE_UNVERIFIED' and len(capture.packets) == 1
    assert getattr(result, field) is None
    if field != 'source_bar_count': assert result.source_bar_count == 16


@pytest.mark.parametrize('fault', ['foreign', 'source_mutation', 'future_completion', 'naive_dispatch',
    'missing_raw_timestamp', 'minute_rollover'])
def test_conflicting_original_witness_refuses_without_rewrite_or_retry(capture, monkeypatch, fault):
    original = capture.client.reqHistoricalData
    def altered(*args, **kwargs):
        if fault == 'minute_rollover':
            capture.clock.current += timedelta(seconds=31)
        result = original(*args, **kwargs)
        if fault == 'foreign':
            return replace(result, dispatched_contract_identity=replace(result.contract_identity, con_id=999))
        if fault == 'source_mutation':
            result.bars[0].close = 987.
        if fault == 'future_completion':
            return replace(result, completed_at_utc=(capture.clock.current + timedelta(seconds=1)).isoformat())
        if fault == 'naive_dispatch':
            return replace(result, request_dispatched_at_utc=capture.clock.current.replace(tzinfo=None).isoformat())
        if fault == 'missing_raw_timestamp':
            return replace(result, raw_bar_timestamps=())
        return result
    monkeypatch.setattr(capture.client, 'reqHistoricalData', altered)
    result = capture.call()
    assert not result.completed and len(capture.packets) == 1 and result.end_received
    assert result.source_bar_count == len(result.raw_source_bars) == 16
    assert result.request_spec.end_date_time == '20261113-14:46:00'
    if fault == 'source_mutation': assert result.raw_source_bars[0]['close'] == 10.1
    if fault == 'minute_rollover': assert result.request_dispatched_at_utc == capture.clock.current.isoformat()


def test_cancelled_acquisition_propagates_without_wire(capture):
    from src.core.acquisition import AcquisitionCancelled, acquisition_scope
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: True):
        capture.call()
    assert capture.packets == []


@pytest.mark.parametrize('change', ['minute', 'window', 'calendar'])
def test_final_checkpoint_revalidates_calendar_and_endpoint_before_wire(capture, monkeypatch, change):
    from src.core import acquisition
    original = acquisition.checkpoint
    calls = []
    def checkpoint():
        original()
        calls.append(True)
        if len(calls) == 2:
            if change == 'minute': capture.clock.current += timedelta(seconds=31)
            elif change == 'window': capture.clock.current = OPEN + timedelta(hours=1)
            else: cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, MARKET_SESSION_COVERAGE=None))
    monkeypatch.setattr(acquisition, 'checkpoint', checkpoint)
    result = capture.call()
    assert not result.completed and capture.packets == []
    assert result.request_spec is None and result.request_dispatched_at_utc is None
