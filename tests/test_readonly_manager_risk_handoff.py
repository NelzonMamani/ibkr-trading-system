"""Synthetic offline ACTUAL manager: canonical cache -> Focus -> real BullFlag -> risk.

Only acquisition/position snapshots and startup housekeeping are fixture supplied;
no pattern, trigger, strategy output, artifact ID or risk result is fabricated.
"""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest

from src.config import config_resolver
from src.core import orchestrator as core_module
from src.core.orchestrator import CoreOrchestrator
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.ross_momentum.patterns import pattern_trace
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.setup_engine.setup_families.bull_flag import BullFlagPattern
from src.risk.risk_engine import RiskEngine
from src.scanner import scanner_runner as ross
from test_news_catalyst_lifecycle_audit import lifecycle
from test_watchlist_between_scan_reassessment import reassessment
from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _row, _payload, _cadence, _age_cache
from test_ross_supported_catalyst_critical_path import _news_and_focus, _saved_shape_verdict, no_broker_mutations
from test_pr1082_trigger_to_intent_terminal_semantics import _base_strategy, _candles, _snapshot
from test_bull_flag_pipeline_end_to_end import _inputs as bull_inputs


@pytest.mark.parametrize('fault', ['none', 'positions', 'stale_bars', 'negative_catalyst', 'stale_quote', 'handoff_expiry', 'integrity'])
def test_actual_manager_canonical_cache_real_bullflag_risk(reassessment, monkeypatch, tmp_path, capsys, fault, no_broker_mutations):
    c = reassessment
    news, _, before = _news_and_focus(c.life, monkeypatch,
        'JPM market roundup' if fault == 'negative_catalyst' else 'JPM reports earnings beat')
    monkeypatch.setattr(core_module, 'datetime', c.life.clock)
    c.row.update(last_price=10.88, bid=10.87, ask=10.89, spread_pct=100*.02/10.88,
                 dollar_volume=19584000., session='RTH_OPEN')
    bundle = c.payload['ross_watchlist_reassessment']
    bundle.update(date=c.life.clock.current.date().isoformat(), session='RTH_OPEN')
    payload = _payload([_row('JPM')], focus=[])
    payload.update(c.payload)
    core, scans, _ = _install_runtime_harness(monkeypatch, [payload])
    monkeypatch.delenv('FORCE_SESSION')  # Use explicit clock/session, no forced runtime session.
    overrides = dict(config_resolver._CONFIG_OVERRIDES)
    overrides.update(NEWS_ENABLED=True, NEWS_CACHE_FILE=str(c.life.store.cache_path), ROSS_ISSUER_QUERY_ENABLED=True,
                     SCANNER_DATA_SOURCE='IBKR', LIVE_EXECUTION_PROBE_MODE=False)
    config_resolver.set_config_overrides(overrides)
    _, policy = core._build_scanner_policy_for_strategy('ross_momentum', 'RTH_OPEN')
    bundle.update(policy=policy, thresholds=ross._gate_thresholds(policy, ross._resolve_runtime_thresholds(policy, 'RTH_OPEN')))
    core.connection_manager._client = object()
    c.provider.market_data_client = core.connection_manager.optional_client
    scanner_stub = core_module.run_scanner_cycle
    def scan(**kwargs):
        ross._PERSISTENT_PROVIDER = c.provider
        return scanner_stub(**kwargs)
    monkeypatch.setattr(core_module, 'run_scanner_cycle', scan)
    core._news_maintenance = NS(read=lambda candidates, request, policy:
        c.life.service.get_news(candidates, request, replace(policy, network_allowed=False,
                                   refresh_mode='cache_only', allow_cache_write=False)), set_active=lambda *args: None)
    strategy = _base_strategy(monkeypatch, tmp_path, state='ready')
    registry = RossPatternRegistry(); registry._patterns = [BullFlagPattern()]
    strategy._pattern_registry = registry
    core.strategy_runner.strategies = [strategy]
    core.strategy_runner._runner_registry = StrategyRunner._build_runner_registry([strategy])
    # Restore the real runner replaced by the existing acquisition harness.
    real_process = StrategyRunner.process.__get__(core.strategy_runner)
    formed = []
    def process(**kwargs):
        intents = real_process(**kwargs)
        formed.extend(intents)
        if fault == 'handoff_expiry':
            c.life.clock.current += timedelta(seconds=121)
        if fault == 'integrity':
            for intent in intents:
                intent.confirmation_passed = False
        return intents
    core.strategy_runner.process = process
    end = c.life.clock.current.replace(second=0, microsecond=0)
    primary = [(10,10.02,9.98,10,1000)]*41 + [(x.open,x.high,x.low,x.close,x.volume) for x in bull_inputs().candles]
    streams = {'1m': _candles(primary,end=end), '5m': _candles(primary,end=end,step_seconds=300),
        '10s': _candles([(10.7,10.75,10.65,10.72,100)]*29+[(10.72,10.9,10.7,10.88,200)],end=end,step_seconds=10)}
    if fault == 'stale_bars':
        streams['10s'] = [replace(x,timestamp=x.timestamp-timedelta(seconds=180)) for x in streams['10s']]
    monkeypatch.setattr(pattern_trace,'get_intraday_bars',lambda *,timeframe='1m',**kw:streams[timeframe])
    snapshot = replace(_snapshot(symbol='JPM'), last=10.88,bid=10.87,ask=10.89,
                       asof_utc=c.life.clock.current,market_timestamp_utc=c.life.clock.current)
    core.market_data_snapshot_manager = NS(batch_snapshots=lambda symbols: ({s:snapshot for s in symbols},[]))
    if fault == 'positions':
        verdict = _saved_shape_verdict(c.life.clock.current)
        monkeypatch.setattr(core,'_resolve_position_truth_cycle',lambda **kw:verdict)
    evaluated = []
    real_risk = core.risk_engine.evaluate_trade_intent
    def evaluate(intent, **kwargs):
        decision = real_risk(intent, **kwargs)
        evaluated.append((intent,decision))
        return decision
    monkeypatch.setattr(core.risk_engine,'evaluate_trade_intent',evaluate)
    artifacts = []
    builder = core_module.build_decision_artifact
    def build(**kwargs):
        artifact = builder(**kwargs)
        artifacts.append((artifact, kwargs))
        return artifact
    monkeypatch.setattr(core_module,'build_decision_artifact',build)
    def forbidden(*args, **kwargs):
        raise AssertionError('No execution submission allowed')
    monkeypatch.setattr(core.execution_engine,'execute_trade',forbidden)
    assert core.run_once() and _cadence(core).focus.symbols == []
    capsys.readouterr()
    _age_cache(_cadence(core).focus,11)
    if fault == 'stale_quote':
        original = c.provider.refresh_quote
        def stale(symbol):
            q = original(symbol)
            q.timestamp_utc = (c.life.clock.current-timedelta(seconds=121)).isoformat()
            return q
        c.provider.refresh_quote = stale
    assert core.run_once()
    out = capsys.readouterr().out
    assert len(scans)==1 and c.life.provider.calls==1
    assert c.life.store.cache_path.read_bytes()==before
    assert '[EXECUTION][SUBMIT]' not in out and 'ORDER_SUBMITTED' not in out
    if fault == 'none':
        assert len(evaluated)==len(artifacts)==len(formed)==1, out
        intent, decision = evaluated[0]
        artifact, arguments = artifacts[0]
        assert not getattr(intent,'synthetic_forced_intent',False) and not getattr(intent,'force_execute',False)
        assert intent.setup_family_id=='BULL_FLAG' and intent.trigger_ready and intent.confirmation_passed
        assert intent.decision_id==artifact.decision_id==decision.decision_id
        assert artifact.source=='CoreOrchestrator' and artifact.run_mode=='READ_ONLY'
        assert artifact.metadata['cycle_id']==core._current_cycle_id and artifact.intents==[intent]
        assert arguments['intents']==[intent]
        assert not decision.allowed and decision.execution_blocked
        assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
        assert 'READ_ONLY mode forbids new executions' in decision.rationale
        assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out
        assert 'DECISION_ARTIFACT_MISSING' not in out and 'RISK_APPROVED' not in out
        assert 'SESSION_BLOCK' not in out and 'ORDER_SIMULATED' not in out
        events = core.event_collector.filter_by_source('CoreOrchestrator')
        assert any(e.event_type=='DECISION_ARTIFACT_CREATED' and e.payload['decision_id']==intent.decision_id for e in events)
        risk_events = core.event_collector.filter_by_source('RiskEngine')
        assert any(e.event_type=='RISK_DECISION' and e.payload['decision_id']==intent.decision_id
                   and 'LIVE_READ_ONLY_BLOCK' in e.payload['reason_codes'] for e in risk_events)
        intent.decision_id=None
        assert RiskEngine().evaluate_trade_intent(intent).reason_code=='DECISION_ARTIFACT_MISSING'
    else:
        assert evaluated==[] and artifacts==[],out
        if fault in {'positions','handoff_expiry','integrity'}:
            assert '[PIPELINE][STRATEGY_OUTPUT] count=1' in out
            reason = {'positions':'POSITION_TRUTH_BLOCK_NEW_ENTRIES','handoff_expiry':'MD_STALE','integrity':'INTENT_REJECTED_BY_EXECUTION_INTEGRITY'}[fault]
            assert reason in out
            assert len(formed)==1 and formed[0].decision_id is None
            assert '[PIPELINE][RISK_INPUT] intents_count=0' in out
            if fault=='positions':
                assert 'reason=INTENT_REJECTED_BY_EXECUTION_INTEGRITY' not in out
            assert 'reason=conflict_or_limit' not in out
            assert 'SESSION_BLOCK' not in out and 'ORDER_SIMULATED' not in out
            assert 'dominant_blocking_reasons=' in out
            assert 'RISK_APPROVED' not in out
            if fault=='positions':
                assert "dominant_blocking_reasons={'POSITION_TRUTH_BLOCK_NEW_ENTRIES': 1}" in out
                assert 'all_removed_by_arbitration=False' in out
        else:
            assert '[PIPELINE][STRATEGY_OUTPUT] count=0' in out


@pytest.mark.parametrize('mode', ['PAPER', 'LIVE'])
def test_non_readonly_manager_does_not_enter_new_artifact_risk_path(monkeypatch, capsys, mode, no_broker_mutations):
    # Isolated mode-boundary control, not a positive strategy/natural proof.
    from test_pr1082_rth_watchlist_continuity import _trade_intent
    row = _row('JPM', catalyst=True)
    core, _, _ = _install_runtime_harness(monkeypatch, [_payload([row], focus=[row])],run_mode=mode)
    raw = _trade_intent('JPM')
    core.strategy_runner.process = lambda **kwargs: [raw]
    def forbidden(*args, **kwargs):
        raise AssertionError('READ_ONLY-only integration entered in another mode or submitted')
    monkeypatch.setattr(core.risk_engine,'evaluate_trade_intent',forbidden)
    monkeypatch.setattr(core_module,'build_decision_artifact',forbidden)
    monkeypatch.setattr(core.execution_engine,'execute_trade',forbidden)
    assert core.run_once()
    out = capsys.readouterr().out
    assert raw.decision_id is None
    assert '[PIPELINE][RISK_INPUT] intents_count=1' in out
    assert '[RISK][DECISION]' not in out
