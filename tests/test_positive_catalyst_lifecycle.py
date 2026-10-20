"""Controlled canonical facts only; no provider/broker calls or JSON writer worker."""
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest

from test_news_catalyst_lifecycle_audit import lifecycle, PUB, CANDIDATE, context
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.strategies.ross_momentum.policy.catalyst_lifecycle import revalidate_handoff, filter_catalyst_rows
from src.scanner import scanner_runner as ross


def snapshot(life):
    return context(life.service.get_news((CANDIDATE,),life.request,life.policy))['catalyst_evidence']


@pytest.mark.parametrize('seconds,valid',[(0,True),(120,True),(121,True),(9000,True),(21600,True),(21600.1,False)])
def test_event_lifetime_is_not_acquisition_cadence(lifecycle, seconds, valid):
    life=lifecycle
    handoff=snapshot(life)
    original=handoff['evidence'][0]['published_at']
    life.clock.current=PUB+timedelta(seconds=seconds)
    decision=revalidate_handoff('JPM',handoff,store=life.store,request=life.request)
    assert decision['qualified'] is valid
    assert decision['acquisition_health']=='degraded'
    assert handoff['evidence'][0]['published_at']==original
    assert life.provider.calls==1


def test_restart_serialized_focus_and_setup_have_no_new_http(lifecycle):
    life=lifecycle
    handoff=json.loads(json.dumps(snapshot(life)))
    life.clock.current=PUB+timedelta(hours=2,minutes=30)
    row=SimpleNamespace(symbol='JPM',catalyst_present=True,catalyst_evidence=handoff)
    restarted=CanonicalNewsEvidenceStore(life.store.cache_path,prep_artifact_loader=lambda:{})
    for stage in ('cached_focus','setup_handoff'):
        accepted=filter_catalyst_rows([row],store=restarted,request=life.request,stage=stage)
        assert len(accepted)==1 and accepted[0].symbol=='JPM'
        assert accepted[0].catalyst_evidence==handoff
        assert accepted[0].news_acquisition_health=='degraded'
        assert accepted[0].catalyst_qualification_reason=='verified_issuer_event_valid'
    assert life.provider.calls==1
    life.clock.current=PUB+timedelta(hours=6,microseconds=1)
    assert not filter_catalyst_rows([row],store=restarted,request=life.request)


def test_failed_and_empty_refresh_keep_original_positive_but_expose_health(lifecycle):
    life=lifecycle
    old=snapshot(life)
    life.clock.current+=timedelta(seconds=121)
    life.provider.failure=True
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    ctx=context(result)
    assert ctx['ross_catalyst_valid'] and not ctx['news_available']
    assert ctx['qualification_reason']=='verified_issuer_event_valid'
    assert ctx['acquisition_health']=='degraded'
    assert ctx['news_provider_status']=='provider_request_failure'
    assert ctx['catalyst_evidence']['evidence'][0]['published_at']==old['evidence'][0]['published_at']
    # Acquisition still becomes due even though positive event remains qualified.
    assert ross._unresolved_ross_news_symbols(['JPM'],{'JPM':ctx})==['JPM']
    life.clock.current+=timedelta(seconds=121)
    life.provider.failure=False;life.provider.articles=()
    ctx=context(life.service.get_news((CANDIDATE,),life.request,life.policy))
    assert ctx['ross_catalyst_valid']
    assert ctx['catalyst_evidence']['evidence'][0]['published_at']==old['evidence'][0]['published_at']


def test_new_retained_veto_invalidates_old_focus_without_http(lifecycle):
    life=lifecycle
    handoff=snapshot(life)
    offering=life.article('JPM announces registered direct offering',PUB-timedelta(hours=5))
    life.store.write({'JPM':(offering,)},life.request)
    life.clock.current=PUB+timedelta(hours=2)
    decision=revalidate_handoff('JPM',handoff,store=life.store,request=life.request)
    assert decision['dilution_veto'] and not decision['qualified']
    assert decision['qualification_reason']=='retained_dilution_veto'
    assert life.provider.calls==1


@pytest.mark.parametrize('change', ['missing','flag_only','wrong_symbol','wrong_issuer','wrong_text','update_only','research','future','no_id'])
def test_cached_flags_and_invalid_facts_are_not_authority(lifecycle,change):
    life=lifecycle
    handoff=json.loads(json.dumps(snapshot(life)))
    # Private empty store prevents the original good witness masking changed facts.
    empty=CanonicalNewsEvidenceStore(life.store.cache_path.parent/'empty.json',prep_artifact_loader=lambda:{})
    if change=='missing':handoff=None
    elif change=='flag_only':handoff={'CONFIRMED':True}
    elif change=='wrong_symbol':handoff['symbol']='AIXI'
    elif change=='wrong_issuer':handoff['issuer']['symbol']='NCPL'
    elif change=='wrong_text':handoff['evidence'][0]['headline']='AAPL reports earnings beat'
    elif change=='update_only':handoff['evidence'][0]['raw']={'timestamp_provenance':{'selected_time_basis':'updated'}}
    elif change=='research':handoff['evidence'][0]['source_tier']='research'
    elif change=='future':handoff['evidence'][0]['published_at']=(life.clock.current+timedelta(seconds=1)).isoformat()
    elif change=='no_id':handoff['evidence'][0]['evidence_id']=None
    assert not revalidate_handoff('JPM',handoff,store=empty,request=life.request)['qualified']


def test_unreadable_store_rejects_without_suppressing_error(lifecycle):
    life=lifecycle;handoff=snapshot(life)
    life.store.cache_path.write_text('{broken')
    decision=revalidate_handoff('JPM',handoff,store=life.store,request=life.request)
    assert not decision['qualified']
    assert decision['qualification_reason']=='canonical_store_unreadable'


@pytest.mark.parametrize('new_veto', [True,False])
def test_actual_merge_direction_reassesses_both_veto_cohorts(lifecycle,new_veto):
    life=lifecycle
    positive=context(life.service.get_news((CANDIDATE,),life.request,life.policy))
    offering=life.article('JPM announces registered direct offering')
    result=ross.NewsBatchResult(candidates=(CANDIDATE,),request=life.request,
        evidence_by_symbol={'JPM':(offering,)})
    veto=context(result)
    fetched,prior=(veto,positive) if new_veto else (positive,veto)
    merged=ross._merge_news_contexts({'JPM':fetched},{'JPM':prior})['JPM']
    assert merged['dilution_flag'] and not merged['ross_catalyst_valid']
    assert any('offering' in row['headline'] for row in merged['catalyst_evidence']['evidence'])
    assert merged['acquisition_reason']==fetched['acquisition_reason']


def test_cached_handoff_returns_current_degraded_health_not_healthy_flags(lifecycle):
    life=lifecycle
    handoff=snapshot(life)
    row={'symbol':'JPM','catalyst_present':True,'catalyst_evidence':handoff,
         'news_acquisition_health':'healthy','news_acquisition_reason':'acquisition_available'}
    life.clock.current+=timedelta(seconds=121)
    refreshed=filter_catalyst_rows([row],store=life.store)[0]
    assert refreshed['news_acquisition_health']=='degraded'
    assert refreshed['news_acquisition_reason']=='acquisition_receipt_expired'
    assert refreshed['catalyst_qualification_reason']=='verified_issuer_event_valid'
    assert row['news_acquisition_health']=='healthy'


@pytest.mark.parametrize('field,value',[('issuer',None),('evidence',None),('evidence','CONFIRMED'),('evidence',[])])
def test_malformed_capsule_rejects_even_with_good_store(lifecycle,field,value):
    life=lifecycle;handoff=snapshot(life);handoff[field]=value
    assert not revalidate_handoff('JPM',handoff,store=life.store)['qualified']


def test_original_manual_selection_authority_does_not_claim_catalyst(lifecycle,capsys):
    life=lifecycle
    row={'symbol':'JPM','watchlist_source':'MANUAL_FOCUS','catalyst_present':False}
    assert filter_catalyst_rows([row],store=life.store)==[row]
    assert 'canonical_event_claimed=false' in capsys.readouterr().out
    assert life.provider.calls==0


def test_orchestrator_cached_focus_expires_before_setup_without_rescan(lifecycle,monkeypatch,capsys):
    from test_pr1082_rth_watchlist_continuity import _row, _payload, _install_runtime_harness, _cadence
    from src.strategies.ross_momentum.policy import catalyst_lifecycle
    life=lifecycle
    row=_row('JPM',catalyst=True)
    row.catalyst_evidence=snapshot(life)
    monkeypatch.setattr(catalyst_lifecycle,'CanonicalNewsEvidenceStore',lambda:life.store)
    orchestrator,scanner_calls,processed=_install_runtime_harness(monkeypatch,[_payload([row],focus=[row])])
    assert orchestrator.run_once() is True
    assert processed==[['JPM']]
    life.clock.current=PUB+timedelta(hours=6,microseconds=1)
    assert orchestrator.run_once() is True
    assert len(scanner_calls)==1 and processed==[['JPM']]
    assert _cadence(orchestrator).focus.symbols==[]
    assert 'qualification_reason=no_valid_canonical_event' in capsys.readouterr().out
    assert life.provider.calls==1


def test_valid_until_is_derived_from_original_publication_not_capsule_flags(lifecycle):
    life=lifecycle;handoff=snapshot(life)
    handoff['publication_max_age_seconds']=999999999
    life.clock.current=PUB+timedelta(hours=2)
    decision=revalidate_handoff('JPM',handoff,store=life.store)
    assert decision['qualified']
    assert decision['valid_until_utc']==(PUB+timedelta(hours=6)).isoformat()
    life.clock.current=PUB+timedelta(hours=6,microseconds=1)
    assert not revalidate_handoff('JPM',handoff,store=life.store)['qualified']


def test_raw_veto_tag_preserves_existing_strip_semantics(lifecycle):
    life=lifecycle;handoff=snapshot(life)
    generic=life.article('JPM market roundup',raw={'catalyst_tag':' offering '})
    life.store.write({'JPM':(generic,)},life.request)
    decision=revalidate_handoff('JPM',handoff,store=life.store)
    assert not decision['qualified'] and decision['dilution_veto']


@pytest.mark.parametrize('historical',[None,False,'healthy'])
def test_malformed_historical_health_is_unknown_not_authority(lifecycle,historical):
    life=lifecycle;handoff=snapshot(life);handoff['acquisition_snapshot']=historical
    decision=revalidate_handoff('JPM',handoff,store=life.store)
    assert decision['qualified'] and decision['acquisition_health']=='degraded'
    assert decision['previous_acquisition_health']=='unknown'


@pytest.mark.parametrize('kind',['future','update_only'])
def test_unqualified_same_id_never_extends_validity(lifecycle,kind):
    life=lifecycle;handoff=snapshot(life)
    original=life.provider.articles[0]
    bad=replace(original,published_at=life.clock.current+timedelta(hours=1))
    if kind=='update_only':bad=replace(bad,raw={'timestamp_provenance':{'selected_time_basis':'updated'}})
    life.store.write({'JPM':(bad,)},life.request)
    decision=revalidate_handoff('JPM',handoff,store=life.store)
    assert decision['qualified']
    assert decision['valid_until_utc']==(PUB+timedelta(hours=6)).isoformat()


@pytest.mark.parametrize('mode,allowed',[('READ_ONLY',False),('LIVE',False),('PAPER',True),('SIM',True)])
def test_existing_explicit_validation_authority_is_separate_from_event(lifecycle,mode,allowed):
    from src.config.config_resolver import set_config_overrides
    set_config_overrides({'ROSS_VALIDATION_OVERRIDE_ENABLED':True})
    row={'symbol':'JPM','catalyst_present':True}
    assert bool(filter_catalyst_rows([row],store=lifecycle.store,mode=mode)) is allowed


def test_later_setup_row_rechecks_expiry_after_slow_first_row(lifecycle,monkeypatch):
    from catalyst_fixtures import canonical_catalyst_fixture
    from src.config.runtime_config import RunMode
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    from src.strategies.ross_momentum.policy import catalyst_lifecycle
    life=lifecycle
    rows=[{'symbol':symbol,'volume':2000000,'catalyst_evidence':canonical_catalyst_fixture(symbol,published=life.clock.fromtimestamp(PUB.timestamp(),PUB.tzinfo))}
          for symbol in ('JPM','EGG')]
    monkeypatch.setattr(catalyst_lifecycle,'CanonicalNewsEvidenceStore',lambda:life.store)
    strategy=RossMomentumStrategyV1()
    built=[]
    def slow_inputs(**kwargs):
        built.append(kwargs['row']['symbol'])
        life.clock.current=PUB+timedelta(hours=6,microseconds=1)
        return None, []
    monkeypatch.setattr('src.strategies.ross_momentum_strategy_v1.build_runtime_pattern_inputs',slow_inputs)
    strategy.process_watchlist(watchlist=rows,snapshots={},session_label='RTH',
        timestamp_utc=life.clock.current.isoformat(),mode=RunMode.READ_ONLY,session_phase='RTH')
    assert built==['JPM']
    assert strategy.last_symbol_terminal_outcomes['EGG']['reason']=='canonical_catalyst_revalidation_failed'
    assert life.provider.calls==0


def test_direct_ross_runner_rejects_opaque_confirmed_flags(lifecycle):
    from src.config.runtime_config import RunMode
    from src.strategies.ross_momentum.runner import RossMomentumRunner
    runner=RossMomentumRunner.__new__(RossMomentumRunner)
    seen=[]
    runner.strategy=SimpleNamespace(process_watchlist=lambda **kwargs:seen.extend(kwargs['watchlist']) or [])
    result=runner.run({'watchlist':[{'symbol':'JPM','catalyst_present':True,'catalyst_status':'CONFIRMED'}],
                       'mode':RunMode.READ_ONLY})
    assert seen==[] and result['trade_intents']==[]
    assert lifecycle.provider.calls==0


def test_setup_boundary_reconciles_focus_and_actual_rejection_cause(lifecycle,monkeypatch,capsys):
    from test_pr1082_rth_watchlist_continuity import _row, _payload, _install_runtime_harness, _cadence
    from src.strategies.ross_momentum.policy import catalyst_lifecycle
    life=lifecycle;row=_row('JPM',catalyst=True);row.catalyst_evidence=snapshot(life)
    monkeypatch.setattr(catalyst_lifecycle,'CanonicalNewsEvidenceStore',lambda:life.store)
    orchestrator,_,processed=_install_runtime_harness(monkeypatch,[_payload([row],focus=[row])])
    received=[]
    def expire_before_handoff(symbols):
        life.clock.current=PUB+timedelta(hours=6,microseconds=1)
        return {},[]
    orchestrator.market_data_snapshot_manager.batch_snapshots=expire_before_handoff
    orchestrator.strategy_runner.receive_watchlist_snapshot=lambda **kwargs:received.append(kwargs['watchlist_symbols'])
    assert orchestrator.run_once() is True
    assert processed==[] and received==[[]]
    assert _cadence(orchestrator).focus.symbols==[]
    output=capsys.readouterr().out
    assert 'strategy_input_count=0' in output
    assert 'CATALYST_HANDOFF:no_valid_canonical_event' in output
    assert 'selected_but_not_evaluated' not in output
