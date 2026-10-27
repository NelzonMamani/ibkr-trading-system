"""Deterministic production admission controls. No acquisition or natural claims."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient

from src.core.acquisition import acquisition_scope, cycle_cache
from src.config.config_resolver import get_config, set_config_overrides
from src.ibkr import market_data_client as md
from src.scanner import scanner_runner as scanner
from test_post_pr1090_market_data_authority import native, native_ticks, contract, client_for
from test_ross_stale_quote_boundary import context, thresholds

class Clock(datetime):
    value = None
    @classmethod
    def now(cls, tz=None):
        return cls.value

NOW = Clock(2026, 10, 26, 16, 41, 28, tzinfo=timezone.utc)

@pytest.fixture(autouse=True)
def clock(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_client
    from src.domain import quote_freshness
    monkeypatch.setattr(quote_freshness, "datetime", Clock)
    Clock.value = NOW
    for module in (md, scanner, ibkr_client):
        monkeypatch.setattr(module, 'datetime', Clock)
    return Clock


def install_ticks(native, monkeypatch, stamp):
    def send(self, req, *args):
        native_ticks(self, req)
        if stamp is None:
            self._ticker_by_req_id[req].lastTime = None
        else:
            self.tickString(req, 45, str(stamp.timestamp()))
    monkeypatch.setattr(EClient, 'reqMktData', send)
    monkeypatch.setattr(native, 'resolve_contract', lambda _: NS(contract=contract()))


def test_future_snapshot_is_rejected_and_retains_broker_time(native, monkeypatch):
    stamp = NOW + timedelta(microseconds=1)
    install_ticks(native, monkeypatch, stamp)
    result = client_for(native).snapshot_stock(contract())
    assert result.timestamp_utc == stamp.isoformat()
    assert 'MD_TIMESTAMP_FUTURE' in result.data_quality_flags
    assert result.snapshot_complete and result.returned_market_data_type == 'LIVE'
    assert not native._ticker_by_req_id


def test_future_cache_insertion_and_reuse_are_not_permission(monkeypatch):
    client = client_for(NS())
    client.last_snapshot_debug = {}
    stamp = (NOW + timedelta(microseconds=1)).isoformat()
    sample = NS(timestamp_utc=stamp, timestamp_source='LAST_TRADE', data_quality_flags=[])
    calls = []
    monkeypatch.setattr(client, '_snapshot_stock_uncached', lambda _: calls.append(1) or sample)
    with acquisition_scope(lambda: False):
        first = client.snapshot_stock('FIXTURE')
        second = client.snapshot_stock('FIXTURE')
        assert first is second and calls == [1]
        assert 'MD_TIMESTAMP_FUTURE' in second.data_quality_flags
        assert second.timestamp_utc == stamp
        assert cycle_cache()  # Retained evidence is not a successful eligibility decision.


@pytest.mark.parametrize('gate', [scanner._evaluate_watchlist_gates, scanner._evaluate_focus_gates])
def test_future_scanner_handoff_cannot_select(gate, thresholds):
    row = context()
    row.update(data_quality_flags=[], quote_timestamp_utc=(NOW + timedelta(microseconds=1)).isoformat())
    assert gate(row, thresholds) == 'DROP_FUTURE_MARKET_DATA'
    assert not row['focus_eligible'] and not row['execution_eligible']

from copy import deepcopy
from dataclasses import replace
from src.domain import quote_freshness as freshness
from src.domain.market_snapshot import MarketSnapshot
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.config.runtime_config import RunMode


def cases():
    maximum = int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS'))
    return [('future', NOW + timedelta(microseconds=1), 'MD_TIMESTAMP_FUTURE'),
            ('zero', NOW, None), ('maximum', NOW - timedelta(seconds=maximum), None),
            ('stale', NOW - timedelta(seconds=maximum, microseconds=1), 'MD_STALE'),
            ('missing', None, 'MD_TIMESTAMP_UNKNOWN')]


@pytest.mark.parametrize('label,stamp,reason', cases())
@pytest.mark.parametrize('boundary', ['shared', 'native', 'snapshot', 'cache', 'watchlist', 'focus', 'handoff'])
def test_inclusive_boundaries_and_missing_authority(native, monkeypatch, clock, thresholds, label, stamp, reason, boundary):
    value = stamp.isoformat() if stamp is not None else None
    if boundary == 'shared':
        assert freshness.quote_time_rejection(value, 'LAST_TRADE', now=NOW) == reason
    elif boundary in {'native', 'snapshot'}:
        install_ticks(native, monkeypatch, stamp)
        result = native.get_market_snapshot('AEMD') if boundary == 'native' else client_for(native).snapshot_stock(contract())
        flags = result.data_quality_flags
        actual = result.market_timestamp_utc if boundary == 'native' else result.timestamp_utc
        assert actual == (stamp if boundary == 'native' else value)
        assert set(flags).intersection(freshness.TIME_REJECTIONS) == ({reason} if reason else set())
        assert not native._market_events and not native._ticker_by_req_id
    elif boundary == 'cache':
        client = client_for(NS())
        client.last_snapshot_debug = {}
        sample = NS(timestamp_utc=value, timestamp_source='LAST_TRADE', data_quality_flags=[])
        calls = []
        monkeypatch.setattr(client, '_snapshot_stock_uncached', lambda _: calls.append(1) or sample)
        with acquisition_scope(lambda: False):
            first = client.snapshot_stock('FIXTURE')
            second = client.snapshot_stock('FIXTURE')
            assert first is second and calls == [1]
            assert set(second.data_quality_flags).intersection(freshness.TIME_REJECTIONS) == ({reason} if reason else set())
            assert second.timestamp_utc == value
    elif boundary in {'watchlist', 'focus'}:
        row = context()
        row.update(data_quality_flags=[], quote_timestamp_utc=value)
        gate = scanner._evaluate_watchlist_gates if boundary == 'watchlist' else scanner._evaluate_focus_gates
        drops = {'MD_TIMESTAMP_FUTURE':'DROP_FUTURE_MARKET_DATA', 'MD_STALE':'DROP_STALE_MARKET_DATA',
                 'MD_TIMESTAMP_UNKNOWN':'DROP_UNKNOWN_MARKET_TIMESTAMP'}
        assert gate(row, thresholds) == (drops[reason] if reason else None)
        assert row['quote_timestamp_utc'] == value
    else:
        row = NS(symbol='FIXTURE', timestamp_utc=NOW.isoformat(), focus_eligible=True,
                 quote_evidence=freshness.quote_evidence(value, 'LAST_TRADE'))
        reasons = {}
        accepted = freshness.filter_quote_rows([row], stage='cached_focus', rejection_reasons=reasons)
        assert accepted == ([] if reason else [row])
        assert reasons == ({'FIXTURE':reason} if reason else {})


@pytest.mark.parametrize('stamp,source', [(NOW.isoformat(), 'UNKNOWN'), (NOW.isoformat(), 'LOCAL_RECEIPT'),
                                         (NOW.replace(tzinfo=None).isoformat(), 'LAST_TRADE'),
                                         ('malformed', 'LAST_TRADE')])
def test_untrusted_time_rejected_despite_current_receipt(stamp, source, thresholds):
    row = context()
    row.update(quote_timestamp_utc=stamp, quote_timestamp_source=source,
               quote_received_at_utc=NOW.isoformat(), data_quality_flags=[])
    assert scanner._evaluate_focus_gates(row, thresholds) == 'DROP_UNKNOWN_MARKET_TIMESTAMP'
    assert freshness.quote_time_rejection(stamp, source, now=NOW) == 'MD_TIMESTAMP_UNKNOWN'
    assert row['quote_timestamp_utc'] == stamp and row['quote_received_at_utc'] == NOW.isoformat()


def test_cache_reages_on_clock_regression_and_never_rehabilitates_rejected_evidence(monkeypatch, clock):
    client = client_for(NS()); client.last_snapshot_debug = {}
    sample = NS(timestamp_utc=NOW.isoformat(), timestamp_source='LAST_TRADE', data_quality_flags=[])
    calls = []
    monkeypatch.setattr(client, '_snapshot_stock_uncached', lambda _: calls.append(1) or sample)
    with acquisition_scope(lambda: False):
        assert client.snapshot_stock('FIXTURE').data_quality_flags == []
        clock.value = NOW - timedelta(microseconds=1)
        assert 'MD_TIMESTAMP_FUTURE' in client.snapshot_stock('FIXTURE').data_quality_flags
        clock.value = NOW + timedelta(seconds=1)
        retained = client.snapshot_stock('FIXTURE')
        assert 'MD_TIMESTAMP_FUTURE' in retained.data_quality_flags
        assert freshness.evidence_rejection(freshness.quote_evidence(retained.timestamp_utc, retained.timestamp_source, retained.data_quality_flags)) == 'MD_TIMESTAMP_FUTURE'
        clock.value = NOW + timedelta(seconds=int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS')), microseconds=1)
        assert 'MD_STALE' in client.snapshot_stock('FIXTURE').data_quality_flags
    assert calls == [1] and sample.timestamp_utc == NOW.isoformat()


def test_future_rejection_does_not_request_shortlist_refresh(thresholds):
    row = context()
    row.update(data_quality_flags=[], quote_timestamp_utc=(NOW + timedelta(microseconds=1)).isoformat())
    scanner._refresh_shortlisted_quote(row, NS(refresh_quote=lambda _: pytest.fail('future quote triggered acquisition')), 'RTH_OPEN', {})
    assert scanner._evaluate_focus_gates(row, thresholds) == 'DROP_FUTURE_MARKET_DATA'


def test_provider_and_candidate_handoff_retain_evidence_without_granting_permission(native, monkeypatch, thresholds, clock):
    from src.scanner.providers import ibkr_provider
    stamp = NOW + timedelta(microseconds=1)
    install_ticks(native, monkeypatch, stamp)
    provider = ibkr_provider.IbkrScannerProvider.__new__(ibkr_provider.IbkrScannerProvider)
    provider.market_data_client = client_for(native)
    monkeypatch.setattr(provider, '_qualified_contract_for_symbol', lambda _: contract())
    monkeypatch.setattr(provider, '_retain_qualified_company_name', lambda _: None)
    quote = provider.get_quote('AEMD')
    assert quote.timestamp_utc == stamp.isoformat() and quote.timestamp_source == 'LAST_TRADE'
    assert 'MD_TIMESTAMP_FUTURE' in quote.data_quality_flags
    row = context()
    row.update(scanner._quote_market_data_provenance(quote), data_quality_flags=list(quote.data_quality_flags))
    metric = scanner._candidate_from_context(row, {'ross_catalyst_valid':True}, thresholds,
                                            drop_reason=None, timestamp_utc=NOW.isoformat())
    assert metric.timestamp_utc == NOW.isoformat()  # Scan time is descriptive only.
    assert metric.quote_evidence['timestamp_utc'] == stamp.isoformat()
    assert freshness.filter_quote_rows([metric], stage='cached_focus') == []
    clock.value = NOW + timedelta(seconds=1)
    assert freshness.filter_quote_rows([metric], stage='setup_handoff') == []  # Sticky rejection.


@pytest.mark.parametrize('which', ['row', 'snapshot', 'missing', 'untrusted'])
def test_actual_ross_setup_rejects_before_pattern_acquisition(monkeypatch, tmp_path, which, capsys):
    from src.strategies import ross_momentum_strategy_v1 as runtime
    from test_pr1082_trigger_to_intent_terminal_semantics import _base_strategy, _watchlist_row, _snapshot
    strategy = _base_strategy(monkeypatch, tmp_path, state='ready')
    row = dict(_watchlist_row(), quote_evidence=freshness.quote_evidence(NOW.isoformat(), 'LAST_TRADE'))
    snapshot = replace(_snapshot(), market_timestamp_utc=NOW, timestamp_source='LAST_TRADE')
    if which == 'row':
        row['quote_evidence'] = freshness.quote_evidence((NOW + timedelta(microseconds=1)).isoformat(), 'LAST_TRADE')
    elif which == 'snapshot':
        snapshot = replace(snapshot, market_timestamp_utc=NOW + timedelta(microseconds=1))
    elif which == 'missing':
        row['quote_evidence'] = None
    else:
        snapshot = replace(snapshot, timestamp_source='UNKNOWN')
    monkeypatch.setattr(runtime, 'build_runtime_pattern_inputs', lambda **_: pytest.fail('invalid quote reached pattern acquisition'))
    result = strategy.process_watchlist(watchlist=[row], snapshots={'UPC':snapshot}, session_label='RTH_OPEN',
                                       timestamp_utc=NOW.isoformat(), mode=RunMode.READ_ONLY, session_phase='RTH_OPEN')
    assert result == []
    assert strategy.last_symbol_terminal_outcomes['UPC']['outcome'] == 'DATA_BLOCKED'
    assert ('MD_TIMESTAMP_FUTURE' if which in {'row','snapshot'} else 'MD_TIMESTAMP_UNKNOWN') in capsys.readouterr().out


@pytest.mark.parametrize('alias', ['RossMomentumStrategyV1', 'ross_momentum', 'RossMomentumStrategy'])
@pytest.mark.parametrize('mode', ['READ_ONLY', 'PAPER', 'LIVE'])
def test_risk_future_rejection_precedes_force_execute(alias, mode):
    from src.models.data_models import TradeIntent
    from src.risk.risk_engine import RiskEngine
    from src.core.stop_controller import StopController
    set_config_overrides({'RUN_MODE':mode, 'EXECUTION_ENABLED':True})
    try:
        intent = TradeIntent(symbol='FIXTURE', direction='LONG', strategy_name=alias, confidence=.9,
                             rationale='offline', decision_id='offline-artifact',
                             quote_evidence={'selection':freshness.quote_evidence((NOW + timedelta(microseconds=1)).isoformat(), 'LAST_TRADE'), 'snapshot':None})
        intent.force_execute = True
        decision = RiskEngine(stop_controller=StopController()).evaluate_trade_intent(intent)
        assert not decision.allowed and decision.execution_blocked
        assert decision.reason_code == 'MD_TIMESTAMP_FUTURE'
        assert intent.quote_evidence['selection']['timestamp_utc'] == (NOW + timedelta(microseconds=1)).isoformat()
    finally:
        set_config_overrides(None)


@pytest.mark.parametrize('delay_stage', ['none', 'before_decision', 'before_emission'])
def test_real_ross_valid_flow_reages_during_pattern_and_decision_work(monkeypatch, tmp_path, clock, delay_stage):
    from test_pr1082_trigger_to_intent_terminal_semantics import _base_strategy, _watchlist_row, _snapshot
    strategy = _base_strategy(monkeypatch, tmp_path, state='ready')
    from test_pr1082_trigger_to_intent_terminal_semantics import FakeRegistry, _detected_three
    strategy._pattern_registry = FakeRegistry([_detected_three('ready')])
    row = _watchlist_row()
    snapshot = _snapshot()
    original_time = row['quote_evidence']['timestamp_utc']
    if delay_stage == 'before_decision':
        run = strategy._pattern_registry.run
        def delayed(*args, **kwargs):
            result = run(*args, **kwargs)
            clock.value += timedelta(seconds=int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS')), microseconds=1)
            return result
        monkeypatch.setattr(strategy._pattern_registry, 'run', delayed)
    elif delay_stage == 'before_emission':
        compute = strategy._decision_engine.compute_decision
        def delayed(*args, **kwargs):
            result = compute(*args, **kwargs)
            clock.value += timedelta(seconds=int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS')), microseconds=1)
            return result
        monkeypatch.setattr(strategy._decision_engine, 'compute_decision', delayed)
    intents = strategy.process_watchlist(watchlist=[row], snapshots={'UPC':snapshot}, session_label='RTH_OPEN',
                                        timestamp_utc=NOW.isoformat(), mode=RunMode.READ_ONLY, session_phase='RTH_OPEN')
    if delay_stage == 'none':
        assert len(intents) == 1, strategy.last_symbol_terminal_outcomes
        assert intents[0].quote_evidence['selection']['timestamp_utc'] == original_time
        assert intents[0].quote_evidence['snapshot']['timestamp_utc'] == snapshot.market_timestamp_utc.isoformat()
        assert freshness.ross_intent_quote_rejection(intents[0], RunMode.READ_ONLY) is None
        clock.value += timedelta(seconds=int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS')), microseconds=1)
        assert freshness.ross_intent_quote_rejection(intents[0], RunMode.READ_ONLY) == 'MD_STALE'
    else:
        assert intents == []
        assert strategy.last_symbol_terminal_outcomes['UPC']['reason'] == 'MD_STALE'
        assert strategy.last_symbol_terminal_outcomes['UPC']['terminal_stage'] == ('decision_quote' if delay_stage == 'before_decision' else 'intent_quote')
    assert row['quote_evidence']['timestamp_utc'] == original_time


def test_actual_orchestrator_cannot_force_approve_future_intent(monkeypatch, clock, capsys):
    from test_pr1082_rth_watchlist_continuity import _row, _payload, _install_runtime_harness, _trade_intent
    row = _row('FIXTURE', catalyst=True)
    orchestrator, _, _ = _install_runtime_harness(monkeypatch, [_payload([row], focus=[row])])
    # Keep this READ_ONLY integration control offline even if another policy vetoes.
    intent = _trade_intent('FIXTURE')
    intent.quote_evidence['selection']['timestamp_utc'] = (NOW + timedelta(microseconds=1)).isoformat()
    orchestrator.strategy_runner.process = lambda **kwargs: [intent]
    orchestrator.portfolio_arbitrator.select_trades = lambda intents, _: intents
    assert get_config('FORCE_RISK_APPROVAL_FOR_TRADE_READY') is True
    assert orchestrator.run_once() is True
    out = capsys.readouterr().out
    assert '[ROSS][QUOTE][INTENT_REJECT] stage=risk_handoff symbol=FIXTURE reason=MD_TIMESTAMP_FUTURE' in out
    assert '[RISK][OVERRIDE] symbol=FIXTURE' not in out
    assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out



def test_actual_cached_focus_revalidates_without_rescan(monkeypatch, clock, capsys):
    from test_pr1082_rth_watchlist_continuity import _row, _payload, _install_runtime_harness, _cadence
    # This control owns an already-acquired immutable broker fact, rather than
    # asking the synthetic scanner to acquire one at its first handoff.
    row = _row('FIXTURE', catalyst=True, quote_factory=None)
    row.quote_evidence = freshness.quote_evidence(NOW, 'LAST_TRADE')
    original = deepcopy(row.quote_evidence)
    orchestrator, scanned, processed = _install_runtime_harness(monkeypatch, [_payload([row], focus=[row])])
    assert orchestrator.run_once() is True
    assert processed == [['FIXTURE']]
    # TopN/list cache remains current; the broker quote independently ages out.
    clock.value += timedelta(seconds=int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS')), microseconds=1)
    assert orchestrator.run_once() is True
    assert len(scanned) == 1 and processed == [['FIXTURE']]
    assert _cadence(orchestrator).focus.symbols == []
    assert row.quote_evidence == original
    assert 'stage=cached_focus symbol=FIXTURE reason=MD_STALE' in capsys.readouterr().out


@pytest.mark.parametrize('which,expected', [('current', True), ('future', False), ('missing', False), ('local', False)])
def test_explicit_manual_choice_still_requires_broker_quote(which, expected):
    row = NS(symbol='MANUAL', watchlist_source='MANUAL_FOCUS', quote_evidence=None)
    stamp = NOW + timedelta(microseconds=1) if which == 'future' else NOW
    snapshot = MarketSnapshot(symbol='MANUAL', bid=5., ask=5.01, last=5., asof_utc=NOW,
                              market_timestamp_utc=stamp if which != 'missing' else None,
                              timestamp_source='LOCAL_RECEIPT' if which == 'local' else 'LAST_TRADE')
    accepted = freshness.filter_quote_rows([row], snapshots={'MANUAL':snapshot}, stage='setup_handoff')
    assert bool(accepted) is expected
    assert row.quote_evidence is None  # Original user-selected row is not rewritten.
    if expected:
        assert accepted[0].quote_evidence['timestamp_utc'] == stamp.isoformat()
        assert accepted[0].watchlist_source == row.watchlist_source


def test_actual_risk_handoff_reages_emitted_intent_after_arbitration(monkeypatch, clock, capsys):
    from test_pr1082_rth_watchlist_continuity import _row, _payload, _install_runtime_harness, _trade_intent, _terminal_payload
    row = _row('FIXTURE', catalyst=True)
    core, _, _ = _install_runtime_harness(monkeypatch, [_payload([row], focus=[row])])
    intent = _trade_intent('FIXTURE')
    ross = next(s for s in core.strategy_runner.strategies if s.name == 'RossMomentumStrategyV1')
    def process(**kwargs):
        ross.last_evaluated_symbols = ['FIXTURE']
        ross.last_symbol_terminal_outcomes = {'FIXTURE': _terminal_payload('FIXTURE', kwargs['timestamp_utc'],
            outcome='INTENT_CREATED', reason='intent_created', trigger_ready_now=True, intent_emitted=True, terminal_stage='intent')}
        return [intent]
    core.strategy_runner.process = process
    gate = core._apply_position_truth_entry_guard
    def delayed(intents, verdict):
        result = gate(intents, verdict)
        clock.value += timedelta(seconds=int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS')), microseconds=1)
        return result
    monkeypatch.setattr(core, '_apply_position_truth_entry_guard', delayed)
    assert core.run_once() is True
    out = capsys.readouterr().out
    assert 'stage=risk_handoff symbol=FIXTURE reason=MD_STALE' in out
    assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out
    assert 'PIPELINE_BREAK_SETUP_TO_INTENT' not in out
    assert "'RISK_BLOCKED': 1" in out
    assert intent.quote_evidence['selection']['timestamp_utc'] == NOW.isoformat()


@pytest.mark.parametrize('label,stamp,reason', cases())
def test_risk_revalidation_keeps_inclusive_bounds_and_readonly(label, stamp, reason):
    # These are eligibility assertions, never permission to submit an order.
    from src.models.data_models import TradeIntent
    from src.risk.risk_engine import RiskEngine
    from src.core.stop_controller import StopController
    set_config_overrides({'RUN_MODE':'READ_ONLY', 'EXECUTION_ENABLED':False})
    try:
        intent = TradeIntent(symbol='FIXTURE', direction='LONG', strategy_name='RossMomentumStrategyV1', confidence=.9,
                             rationale='offline', decision_id='offline', quote_evidence={
                                 'selection':freshness.quote_evidence(stamp.isoformat() if stamp is not None else None, 'LAST_TRADE'), 'snapshot':None})
        decision = RiskEngine(stop_controller=StopController()).evaluate_trade_intent(intent)
        if reason:
            assert decision.reason_code == reason
        else:
            assert decision.reason_code not in freshness.TIME_REJECTIONS
        assert not decision.allowed  # READ_ONLY remains a separate restriction.
    finally:
        set_config_overrides(None)


def test_local_receipt_only_native_snapshot_never_becomes_broker_time(native, monkeypatch):
    install_ticks(native, monkeypatch, None)
    send = EClient.reqMktData
    def local_only(self, req, *args):
        send(self, req, *args)
        self._ticker_by_req_id[req].time = NOW
        self._ticker_by_req_id[req].receivedAt = NOW
    monkeypatch.setattr(EClient, 'reqMktData', local_only)
    snapshot = native.get_market_snapshot('AEMD')
    assert snapshot.market_timestamp_utc is None
    assert snapshot.timestamp_source == 'UNKNOWN'
    assert 'MD_TIMESTAMP_UNKNOWN' in snapshot.data_quality_flags
    assert snapshot.received_at_utc == NOW


def test_explicit_future_rejection_flag_cannot_be_bypassed_by_current_time():
    intent = NS(strategy_name='ross_momentum', quote_evidence={
        'selection':freshness.quote_evidence(NOW.isoformat(), 'LAST_TRADE'), 'snapshot':None},
        data_quality_flags=['MD_TIMESTAMP_FUTURE'])
    assert freshness.ross_intent_quote_rejection(intent, RunMode.PAPER) == 'MD_TIMESTAMP_FUTURE'
