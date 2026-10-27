"""SYNTHETIC joined boundary proof, not a natural observation or paper acceptance.

Reuse canonical publication/cache, normal Focus gates, real BullFlag detector,
real trigger/decision, position-truth guard and RiskEngine. Core's active-manager
risk markers are NOT a call to RiskEngine: that component is tested separately
on the same raw strategy intent, never by bypassing the ownership guard in Core.
"""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import pytest

from src.config import config_resolver
from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.domain import quote_freshness
from src.ibkr.position_snapshot import BrokerPositionResult
from src.execution import position_truth
from src.execution.position_truth import PositionTruthConfig, collect_broker_position_snapshot, reconcile_position_truth
from src.risk.risk_engine import RiskEngine
from src.scanner import scanner_runner as ross
from src.setup_engine.setup_families.bull_flag import BullFlagPattern
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns import pattern_trace
from test_news_catalyst_lifecycle_audit import lifecycle, CANDIDATE
from test_pr1082_trigger_to_intent_terminal_semantics import _base_strategy, _candles, _watchlist_row, _snapshot
from test_bull_flag_pipeline_end_to_end import _inputs as bull_inputs

@pytest.fixture(autouse=True)
def no_broker_mutations(monkeypatch):
    from ibapi.client import EClient
    def forbidden(*args,**kwargs):
        raise AssertionError('No broker mutation in synthetic critical-path proof')
    monkeypatch.setattr(EClient,'placeOrder',forbidden)
    monkeypatch.setattr(EClient,'cancelOrder',forbidden)


SUPPORTED=[
 ('JPM reports earnings beat','EARNINGS'),
 ('JPM receives FDA approval','FDA'),
 ('JPM wins new contract','CONTRACT'),
 ('JPM receives upgrade','ANALYST_ACTION'),
 ('JPM releases press release','PRESS_RELEASE'),
 ('JPM launches AI platform','TECH_CATALYST'),
 ('JPM launches bitcoin platform','CRYPTO_CATALYST'),
 ('JPM launches electric vehicle platform','EV_CATALYST'),
 ('JPM launches defense platform','DEFENSE_CATALYST'),
]


def _news_and_focus(life,monkeypatch,title):
    # Existing premarket publication remains within6h at synthetic normal RTH.
    life.clock.current=life.clock.current.replace(hour=13,minute=35,second=30,microsecond=0)
    overrides=dict(config_resolver._CONFIG_OVERRIDES)
    overrides.update(RUN_MODE='READ_ONLY',RUN_MODE_EFFECTIVE='READ_ONLY',EXECUTION_ENABLED=False,
        MANUAL_FOCUS_ENABLED=False,ROSS_VALIDATION_OVERRIDE_ENABLED=False,SELECTED_STRATEGY='ross_momentum')
    set_config_overrides(overrides)
    monkeypatch.setattr(quote_freshness,'datetime',life.clock)
    monkeypatch.setattr(position_truth,'datetime',life.clock)
    monkeypatch.setattr(pattern_trace,'datetime',life.clock)
    life.provider.articles=(life.article(title),)
    cold=life.service.get_news((CANDIDATE,),life.request,life.policy)
    assert cold.evidence_for_symbol('JPM')[0].published_at==life.provider.articles[0].published_at
    before=life.store.cache_path.read_bytes()
    cached=life.service.get_news((CANDIDATE,),life.request,replace(life.policy,
        network_allowed=False,refresh_mode='cache_only',allow_cache_write=False))
    assert life.provider.calls==1 and life.store.cache_path.read_bytes()==before
    news=ross._ross_news_contexts_from_news_intelligence_result(cached)['JPM']
    policy=ross.RossPolicy().stock_selection
    thresholds=ross._gate_thresholds(policy,ross._resolve_runtime_thresholds(policy,'RTH_OPEN'))
    row={**_watchlist_row(symbol='JPM'),'company_name':CANDIDATE.company_name,
        'session':'RTH_OPEN','last_price':10.88,'bid':10.87,'ask':10.89,
        'pct_change':25.,'rvol_phase':10.,'rvol_discovery':10.,'rvol':10.,
        'float_shares':8000000,'spread_pct':100*.02/10.88,'dollar_volume':19584000.,
        'quote_timestamp_utc':life.clock.current.isoformat(),'quote_timestamp_source':'LAST_TRADE'}
    focus=ross._select_ross_focus_contexts([row],{'JPM':news},thresholds,
        run_mode=RunMode.READ_ONLY,news_enabled=True,validation_override_active=False,
        catalyst_decision=None,session_label='RTH_OPEN',symbol_contexts={},focus_limit=1)
    return news,focus,before


def _real_pattern_intents(life,monkeypatch,tmp_path,news,focus,stale=False):
    strategy=_base_strategy(monkeypatch,tmp_path,state='ready')
    registry=RossPatternRegistry();registry._patterns=[BullFlagPattern()]
    strategy._pattern_registry=registry
    end=life.clock.current.replace(second=0,microsecond=0)
    primary=[(10,10.02,9.98,10,1000)]*41+[(c.open,c.high,c.low,c.close,c.volume) for c in bull_inputs().candles]
    streams={'1m':_candles(primary,end=end),'5m':_candles(primary,end=end,step_seconds=300),
        '10s':_candles([(10.7,10.75,10.65,10.72,100)]*29+[(10.72,10.9,10.7,10.88,200)],end=end,step_seconds=10)}
    if stale:streams['10s']=[replace(c,timestamp=c.timestamp-timedelta(seconds=180)) for c in streams['10s']]
    monkeypatch.setattr(pattern_trace,'get_intraday_bars',lambda *,timeframe='1m',**kw:streams[timeframe])
    # Carry actual canonical evidence, not a CONFIRMED flag or synthetic setup.
    rows=[{**row,'catalyst_evidence':news['catalyst_evidence'],'catalyst_present':news['ross_catalyst_valid']} for row in focus]
    snapshot=replace(_snapshot(symbol='JPM'),last=10.88,bid=10.87,ask=10.89,
        asof_utc=life.clock.current,market_timestamp_utc=life.clock.current)
    intents=strategy.process_watchlist(watchlist=rows,snapshots={'JPM':snapshot},
        session_label='RTH_OPEN',session_phase='RTH_OPEN',mode=RunMode.READ_ONLY,
        timestamp_utc=life.clock.current.isoformat())
    return strategy,intents


def _saved_shape_verdict(now):
    # Synthetic five nonzero broker-only positions; no real holding values.
    # No broker connection, adoption, order cancellation or quantity change occurs.
    quantities={f'SYNTH{i}':float(i) for i in range(1,6)}
    class SavedShape:
        def position_snapshot(self):
            return BrokerPositionResult(tuple(SimpleNamespace(symbol=s,position=q,account='TEST')
                for s,q in quantities.items()),'COMPLETE','TEST',now)
    broker=collect_broker_position_snapshot(SavedShape(),as_of=now,
        config=PositionTruthConfig(broker_required=True,run_mode=RunMode.READ_ONLY))
    snapshot,verdict=reconcile_position_truth(broker,{},as_of=now,live_broker_mode=True)
    assert len(snapshot.mismatches)==5 and all(m.mismatch_type=='BROKER_ONLY_POSITION' for m in snapshot.mismatches)
    assert verdict.block_new_entries and verdict.block_exits and verdict.critical_mismatch_count==5
    return verdict


@pytest.mark.parametrize('title,event_class',SUPPORTED)
def test_supported_event_to_intent_exposes_ownership_and_missing_risk_artifact(lifecycle,monkeypatch,tmp_path,title,event_class):
    life=lifecycle
    news,focus,before=_news_and_focus(life,monkeypatch,title)
    assert len(focus)==1 and news['catalyst_type']==event_class and news['ross_catalyst_valid']
    strategy,intents=_real_pattern_intents(life,monkeypatch,tmp_path,news,focus)
    assert len(intents)==1,strategy.last_symbol_terminal_outcomes
    intent=intents[0]
    assert intent.setup_family_id=='BULL_FLAG' and intent.trigger_ready and intent.confirmation_passed
    assert not getattr(intent,'synthetic_forced_intent',False)
    assert strategy.last_symbol_terminal_outcomes['JPM']['intent_emitted']
    # Production Core guard is AFTER strategy formation and BEFORE risk-input
    # admission. Preserve the raw object, but never pass it around that guard.
    verdict=_saved_shape_verdict(life.clock.current)
    assert CoreOrchestrator._apply_position_truth_entry_guard(intents,verdict)==[]
    assert len(intents)==1  # Formation evidence remains, admission remains blocked.
    # Independent actual RiskEngine API proof: not a claim Core called it.
    decision=RiskEngine().evaluate_trade_intent(intent)
    assert not decision.allowed and decision.execution_blocked
    assert intent.decision_id is None
    assert decision.reason_code=='DECISION_ARTIFACT_MISSING'
    print('SYNTHETIC_JOINED_GAP',event_class,decision.reason_code)
    assert decision.setup_family_id==intent.setup_family_id and decision.trigger_id==intent.trigger_id
    assert life.provider.calls==1 and life.store.cache_path.read_bytes()==before


@pytest.mark.parametrize('fault',['nonqualifying','offering','stale_bars'])
def test_joined_path_never_manufactures_intents(lifecycle,monkeypatch,tmp_path,fault):
    title='JPM market roundup' if fault=='nonqualifying' else 'JPM announces registered direct offering' if fault=='offering' else SUPPORTED[0][0]
    news,focus,_=_news_and_focus(lifecycle,monkeypatch,title)
    if fault!='stale_bars':
        assert focus==[] and not news['ross_catalyst_valid']
    else:
        assert focus
        strategy,intents=_real_pattern_intents(lifecycle,monkeypatch,tmp_path,news,focus,stale=True)
        assert intents==[] and not strategy.last_symbol_terminal_outcomes['JPM']['intent_emitted']
