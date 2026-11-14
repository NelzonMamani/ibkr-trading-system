"""Default-off next-session contract; all schedules and external facts are synthetic."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, date, timedelta, timezone
from itertools import permutations
import json
from types import SimpleNamespace as NS

import pytest

from src.config import config_resolver as cfg
from src.market_data.session_pct_change import covered_opening_window
from src.news.evidence_store import (retained_evidence, publication_facts, auxiliary_veto_version,
    original_publication_binding, summarize_news_evidence)
from src.news.news_intelligence_contract import NewsRequest
from src.scanner import scanner_runner as ross
from src.strategies.ross_momentum.policy import catalyst_policy as cp
from src.strategies.ross_momentum.policy.catalyst_lifecycle import revalidate_handoff, retained_dilution
from test_news_catalyst_lifecycle_audit import lifecycle, CANDIDATE
from test_watchlist_between_scan_reassessment import reassessment

UTC = timezone.utc
NOW = datetime(2026, 11, 13, 14, 40, tzinfo=UTC)
PUB = datetime(2026, 11, 12, 22, 55, tzinfo=UTC)


def receipt(start, end, *, holidays=(), halves=(), early='13:00'):
    """Explicit fixture declaration, not operational calendar certification."""
    rows = {}
    cursor = date.fromisoformat(start)
    while cursor <= date.fromisoformat(end):
        if cursor.weekday() >= 5 or cursor in holidays:
            rows[cursor.isoformat()] = dict(status='CLOSED', reason='weekend' if cursor.weekday() >= 5 else 'holiday')
        else:
            close = early if cursor in halves else '16:00'
            rows[cursor.isoformat()] = dict(status='OPEN', pre_start='04:00', rth_open='09:30',
                rth_close=close, opening_end=min('10:30', close))
        cursor += timedelta(days=1)
    return dict(schema='market.session_coverage.v1', authority='NYSE',
        source_url='https://www.nyse.com/markets/hours-calendars', version='synthetic-v1',
        review_reference='offline synthetic fixture; no operational enrollment', days=rows)


def configure(life, monkeypatch, *, now=NOW, start='2026-11-12', end='2026-11-13',
              holidays=(), halves=(), enabled=True, limit=1):
    for key in ('FORCE_SESSION', 'SESSION_OVERRIDE', 'MARKET_SESSION_OVERRIDE'):
        monkeypatch.delenv(key, raising=False)
    life.clock.current = now
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, ROSS_NEXT_SESSION_CATALYST_ENABLED=enabled,
        ROSS_ISSUER_QUERY_ENABLED=True, SESSION_PHASE_OVERRIDE=None, NEWS_MAX_ENTRIES_PER_SYMBOL=limit,
        MARKET_HOLIDAYS=set(holidays), MARKET_HALF_DAYS=set(halves),
        MARKET_SESSION_COVERAGE=json.dumps(receipt(start, end, holidays=holidays, halves=halves))))
    life.request = ross._ross_news_request()
    life.policy = ross._ross_retrieval_policy(refresh_mode='force_refresh', network_allowed=True)
    return life


def article(life, key='B', title='JPM reports Q3 earnings beat', published=PUB):
    item = life.article(title, published)
    return replace(item, evidence_id=key, url='https://fixture.invalid/'+key, first_seen_at=item.published_at,
        raw={'timestamp_provenance': dict(selected_time_basis='published',
             published_original=published.isoformat(), published_utc=published.isoformat()), 'source_fact': key})


def decision(life, item):
    return cp.assess_issuer_event('JPM', item, (CANDIDATE,), request=life.request)


@pytest.mark.parametrize('now,expected', [
    ('2026-11-13T08:59:59.999999+00:00', False),
    ('2026-11-13T09:00:00+00:00', True),
    ('2026-11-13T14:30:00+00:00', True),
    ('2026-11-13T15:29:59.999999+00:00', True),
    ('2026-11-13T15:30:00+00:00', False),
    ('2026-11-13T21:00:00+00:00', False),
])
def test_actual_pre_opening_and_strict_expiry(lifecycle, monkeypatch, now, expected):
    life = configure(lifecycle, monkeypatch, now=datetime.fromisoformat(now))
    row = decision(life, article(life))
    assert row['qualified'] is expected
    if expected:
        assert row['temporal_authority']['route'] == 'next_session_opening'
        assert row['age_seconds'] > 21600
        assert row['temporal_authority']['calendar']['target_session'] == '2026-11-13'


@pytest.mark.parametrize('offset,expected', [(0, True), (-1e-6, False)])
def test_exact_previous_close_boundary(lifecycle, monkeypatch, offset, expected):
    life = configure(lifecycle, monkeypatch)
    item = article(life, published=datetime(2026, 11, 12, 21, tzinfo=UTC)+timedelta(seconds=offset))
    assert decision(life, item)['qualified'] is expected


@pytest.mark.parametrize('offset,expected', [(0, True), (1e-6, False)])
def test_ordinary_six_hour_inclusive_route_independent_of_unknown_calendar(lifecycle, monkeypatch, offset, expected):
    life = configure(lifecycle, monkeypatch)
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, MARKET_SESSION_COVERAGE=''))
    life.request = ross._ross_news_request()
    item = article(life, published=NOW-timedelta(seconds=21600+offset))
    assert decision(life, item)['qualified'] is expected


def test_open_publication_is_ordinary_and_remains_valid_after_extra_expiry(lifecycle, monkeypatch):
    life = configure(lifecycle, monkeypatch, now=datetime(2026, 11, 13, 14, 30, tzinfo=UTC))
    item = article(life, published=life.clock.current)
    assert decision(life, item)['temporal_authority']['route'] == 'ordinary_six_hour'
    life.clock.current = datetime(2026, 11, 13, 15, 30, tzinfo=UTC)
    life.request = ross._ross_news_request()
    assert decision(life, item)['qualified']
    assert not decision(life, article(life))['qualified']


@pytest.mark.parametrize('start,end,now,pub,holidays,halves,previous_close', [
    ('2026-11-13','2026-11-16','2026-11-16T14:40:00+00:00','2026-11-13T22:55:00+00:00',(),(),'2026-11-13T21:00:00+00:00'),
    ('2026-03-06','2026-03-09','2026-03-09T13:40:00+00:00','2026-03-06T22:55:00+00:00',(),(),'2026-03-06T21:00:00+00:00'),
    ('2026-10-30','2026-11-02','2026-11-02T14:40:00+00:00','2026-10-30T22:55:00+00:00',(),(),'2026-10-30T20:00:00+00:00'),
    ('2026-07-02','2026-07-06','2026-07-06T13:40:00+00:00','2026-07-02T22:55:00+00:00',('2026-07-03',),(),'2026-07-02T20:00:00+00:00'),
    ('2026-12-31','2027-01-04','2027-01-04T14:40:00+00:00','2026-12-31T22:55:00+00:00',('2027-01-01',),(),'2026-12-31T21:00:00+00:00'),
    ('2026-11-27','2026-11-30','2026-11-30T14:40:00+00:00','2026-11-27T18:00:00+00:00',(),('2026-11-27',),'2026-11-27T18:00:00+00:00'),
])
def test_covered_nontrading_days_dst_year_and_early_close(lifecycle, monkeypatch, start, end, now, pub, holidays, halves, previous_close):
    now, pub = datetime.fromisoformat(now), datetime.fromisoformat(pub)
    life = configure(lifecycle, monkeypatch, now=now, start=start, end=end,
        holidays=tuple(map(date.fromisoformat, holidays)), halves=tuple(map(date.fromisoformat, halves)))
    item = article(life, published=pub)
    row = decision(life, item)
    assert row['qualified'], row
    assert row['temporal_authority']['calendar']['previous_close'] == previous_close
    assert row['temporal_authority']['calendar']['target_session'] == end


def test_weekend_closed_and_second_session_cannot_carry(lifecycle, monkeypatch):
    life = configure(lifecycle, monkeypatch, now=datetime(2026,11,16,14,40,tzinfo=UTC), start='2026-11-13',end='2026-11-17')
    item = article(life, published=datetime(2026,11,13,22,55,tzinfo=UTC))
    assert decision(life,item)['qualified']
    life.clock.current = datetime(2026,11,17,14,40,tzinfo=UTC)
    life.request = ross._ross_news_request()
    assert not decision(life,item)['qualified']
    life.clock.current = datetime(2026,11,14,14,40,tzinfo=UTC)
    life.request = ross._ross_news_request()
    assert not decision(life,item)['qualified']


@pytest.mark.parametrize('fault', ['empty','missing_day','wrong_close','closed_weekday','missing_source','duplicate','half_conflict','source_conflict','precision','override_env','override_config'])
def test_coverage_and_override_refusals_preserve_ordinary_route(lifecycle, monkeypatch, fault):
    life = configure(lifecycle, monkeypatch)
    value = receipt('2026-11-12','2026-11-13')
    if fault == 'empty': value = {}
    elif fault == 'missing_day': del value['days']['2026-11-12']
    elif fault == 'wrong_close': value['days']['2026-11-12']['rth_close']='13:00'
    elif fault == 'closed_weekday': value['days']['2026-11-12']={'status':'CLOSED'}
    elif fault == 'missing_source': value['source_url']=''
    elif fault == 'source_conflict': value['authority']='NASDAQ'
    elif fault == 'precision':
        from datetime import time as clocktime
        cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,MARKET_HALF_DAYS={date(2026,11,12)},MARKET_EARLY_CLOSE_TIME=clocktime(13,0,30)))
        value['days']['2026-11-12']['rth_close']='13:00'
    elif fault == 'override_env': monkeypatch.setenv('FORCE_SESSION','PRE')
    elif fault == 'override_config': cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, SESSION_PHASE_OVERRIDE='PRE'))
    elif fault == 'half_conflict': cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, MARKET_HALF_DAYS={date(2026,11,12)}))
    text = json.dumps(value)
    if fault == 'duplicate': text=text.replace('"schema":', '"schema":"conflict", "schema":',1)
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, MARKET_SESSION_COVERAGE=text))
    life.request=ross._ross_news_request()
    assert covered_opening_window(NOW) is None
    assert not decision(life,article(life))['qualified']
    assert decision(life,article(life,published=NOW-timedelta(minutes=5)))['qualified']


@pytest.mark.parametrize('fault', ['off','other_strategy','history','no_original','updated','conflict','first_seen','future','unknown','preview','foreign','other_owner'])
def test_scope_original_time_and_non_time_gates(lifecycle, monkeypatch, fault):
    life=configure(lifecycle,monkeypatch)
    item=article(life)
    if fault=='off': cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,ROSS_NEXT_SESSION_CATALYST_ENABLED=False))
    elif fault=='other_strategy': life.request=replace(life.request,strategy_id='unrelated')
    elif fault=='history': life.request=replace(life.request,query_start_utc=PUB-timedelta(hours=1),query_end_utc=NOW)
    elif fault=='no_original': item=replace(item,raw={})
    elif fault=='updated': item=replace(item,raw={'timestamp_provenance':{'selected_time_basis':'updated'}})
    elif fault=='conflict':
        raw=deepcopy(item.raw);raw['timestamp_provenance']['published_utc']=NOW.isoformat();item=replace(item,raw=raw)
    elif fault=='first_seen': item=replace(item,first_seen_at=PUB-timedelta(seconds=1))
    elif fault=='future': item=article(life,published=NOW+timedelta(seconds=1))
    elif fault=='unknown': item=replace(item,published_at=None)
    elif fault=='preview': item=replace(item,headline='JPM previews Q3 earnings?')
    elif fault=='foreign': item=replace(item,headline='$JPM.TO reports Q3 earnings')
    elif fault=='other_owner': item=replace(item,headline='JPM reports Q3 earnings of Rival Company')
    assert not decision(life,item)['qualified']


def test_default_request_and_decision_remain_unchanged(lifecycle, monkeypatch):
    life=configure(lifecycle,monkeypatch,enabled=False)
    assert life.request.max_evidence_per_symbol==2
    assert 'protected_retention_contract' not in life.request.metadata
    assert not decision(life,article(life))['qualified']
    positive=decision(life,article(life,published=NOW-timedelta(minutes=1)))
    assert positive['qualified'] and 'temporal_authority' not in positive


def pressure_facts(life):
    a=article(life,'A','JPM market bulletin',NOW-timedelta(seconds=30))
    b=article(life)
    c=article(life,'C','JPM market bulletin',PUB-timedelta(days=1))
    veto=article(life,'C','JPM announces registered direct offering',NOW-timedelta(minutes=5))
    return a,b,c,veto


def test_n_plus_three_versions_are_bounded_deterministic_and_do_not_renew(lifecycle, monkeypatch):
    life=configure(lifecycle,monkeypatch)
    facts=pressure_facts(life)
    signatures=set()
    for ordering in permutations(facts):
        selected=retained_evidence(ordering,life.request)
        assert len(selected)==4
        assert {row.evidence_id for row in selected}=={'A','B','C'}
        auxiliary=next(row for row in selected if auxiliary_veto_version(row))
        assert auxiliary.published_at==facts[2].published_at and auxiliary.stale
        assert auxiliary.raw['timestamp_provenance']==facts[3].raw['timestamp_provenance']
        assert original_publication_binding(auxiliary)['observed_published_ts']==facts[3].published_at.timestamp()
        assert retained_dilution(selected)
        summary=summarize_news_evidence('JPM',selected,request=life.request)
        assert summary.evidence_count==3 and summary.fresh_evidence_count==1
        signatures.add(tuple((row.headline,row.published_at.isoformat()) for row in selected))
    assert len(signatures)==1


def test_offering_then_positive_cannot_erase_or_renew(lifecycle, monkeypatch):
    life=configure(lifecycle,monkeypatch)
    offering=article(life,'C','JPM announces registered direct offering',PUB)
    update=article(life,'C','JPM reports Q3 earnings beat',NOW-timedelta(seconds=10))
    selected=retained_evidence((update,offering),life.request)
    assert len(selected)==1 and selected[0].published_at==PUB
    assert retained_dilution(selected) and not decision(life,selected[0])['qualified']


def test_store_and_generic_writes_keep_positive_veto_anchor_and_disable_veto(lifecycle, monkeypatch):
    life=configure(lifecycle,monkeypatch)
    facts=pressure_facts(life)
    life.provider.articles=facts
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    assert len(result.evidence_for_symbol('JPM'))==4
    context=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert not context['ross_catalyst_valid'] and context['dilution_flag']
    assert context['news_count']==1 and context['fresh_news_count']==1
    generic=NewsRequest(strategy_id='unrelated',max_evidence_per_symbol=1)
    for index in range(3):
        later=article(life,'D'+str(index),'JPM market bulletin',NOW-timedelta(seconds=3-index))
        life.store.write({'JPM':(later,)},generic)
    rows=life.store.read((CANDIDATE,),life.request).evidence_by_symbol['JPM']
    assert len(rows)==4 and retained_dilution(rows)
    assert any(row.evidence_id=='B' for row in rows)
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,ROSS_NEXT_SESSION_CATALYST_ENABLED=False))
    life.store.write({'JPM':(article(life,'E','JPM reports Q3 earnings beat',NOW),)},generic)
    current=life.store.read((CANDIDATE,),ross._ross_news_request()).evidence_by_symbol['JPM']
    assert retained_dilution(current)
    assert all(row.publication_count==len(publication_facts(current)) for row in publication_facts(current))
    verdict=revalidate_handoff('JPM',context['catalyst_evidence'],store=life.store)
    assert not verdict['qualified'] and verdict['dilution_veto']


def test_calendar_change_same_second_invalidates_cached_authority(lifecycle, monkeypatch):
    life=configure(lifecycle,monkeypatch)
    life.provider.articles=(article(life),)
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    first=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert first['ross_catalyst_valid'] and first['stale_news_count']==1
    revised=receipt('2026-11-12','2026-11-13');revised['version']='synthetic-v2'
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,MARKET_SESSION_COVERAGE=json.dumps(revised)))
    second=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert not second['ross_catalyst_valid']
    current_request=ross._ross_news_request()
    current=life.service.get_news((CANDIDATE,),current_request,replace(life.policy,network_allowed=False,refresh_mode='cache_only'))
    assert ross._ross_news_contexts_from_news_intelligence_result(current)['JPM']['ross_catalyst_valid']


def test_handoff_expiry_legacy_binding_and_current_canonical_reclassification(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch)
    life.provider.articles=(article(life),)
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    handoff=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['catalyst_evidence']
    assert revalidate_handoff('JPM',handoff,store=life.store)['qualified']
    life.store.cache_path.unlink()  # Synthetic empty canonical authority, not operational recovery clearing.
    assert revalidate_handoff('JPM',handoff,store=life.store)['qualified']
    forged=deepcopy(handoff)
    for row in forged['temporal_bindings'].values(): row['calendar']['target_session']='2026-11-16'
    assert not revalidate_handoff('JPM',forged,store=life.store)['qualified']
    legacy={key:value for key,value in handoff.items() if key not in {'next_session_contract','temporal_bindings'}}
    assert not revalidate_handoff('JPM',legacy,store=life.store)['qualified']
    life.clock.current=datetime(2026,11,13,15,30,tzinfo=UTC)
    assert not revalidate_handoff('JPM',handoff,store=life.store)['qualified']


def test_degraded_acquisition_preserves_positive_but_not_expiry(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch)
    life.provider.articles=(article(life),)
    life.service.get_news((CANDIDATE,),life.request,life.policy)
    life.provider.failure=True
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    context=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert context['ross_catalyst_valid'] and context['acquisition_health']=='degraded'
    assert context['stale_news_count']==1 and context['gam_ea_eligible'] is False
    life.clock.current=datetime(2026,11,13,15,30,tzinfo=UTC)
    assert not ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['ross_catalyst_valid']


def test_actual_fetch_absolute_close_bound_and_stable_acquisition_profile(lifecycle,monkeypatch):
    import time
    from email.utils import formatdate
    from src.news import news_fetcher
    from src.news.news_intelligence_service import _acquisition_profile
    from src.news.rss_lifecycle import RssFetchLifecycle
    from test_issuer_query_rss import feed
    life=configure(lifecycle,monkeypatch)
    first=_acquisition_profile(CANDIDATE,life.request,life.policy,batch_candidates=(CANDIDATE,))
    life.clock.current+=timedelta(minutes=5)
    current=ross._ross_news_request()
    second=_acquisition_profile(CANDIDATE,current,life.policy,batch_candidates=(CANDIDATE,))
    assert first==second
    close=datetime(2026,11,12,21,tzinfo=UTC)
    rows=[NS(title='JPM reports Q3 earnings beat',summary='',link='https://fixture.invalid/'+str(offset),
        published=formatdate((close+timedelta(seconds=offset)).timestamp(),usegmt=True),
        published_parsed=time.gmtime((close+timedelta(seconds=offset)).timestamp())) for offset in (0,-1)]
    def fetch(*args,**kwargs):
        life.clock.current+=timedelta(seconds=10)
        return feed(rows)
    monkeypatch.setattr(news_fetcher,'_fetch_feed',fetch)
    owner=RssFetchLifecycle()
    try:
        found,_=news_fetcher.fetch_headlines_for_symbols(['JPM'],['https://fixture.invalid/rss'],lookback_hours=6,
            source_tier='operational_query',symbol_metadata={'JPM':{'company_name':CANDIDATE.company_name}},
            retention_selector=cp.select_qualification_evidence,retention_request=life.request,lifecycle=owner)
    finally:
        assert owner.wait_for_cleanup(2)['cleanup_complete']
    assert len(found['JPM'])==1 and found['JPM'][0].published_ts==close.timestamp()
    assert cp.assess_issuer_event('JPM',found['JPM'][0],request=life.request)['qualified']


@pytest.mark.parametrize('control',['positive','off','veto','missing_calendar','override','weekend_positive'])
def test_next_session_canonical_to_actual_core_focus(reassessment,monkeypatch,control):
    from src.core import orchestrator as core_module
    from test_pr1082_rth_watchlist_continuity import _install_runtime_harness,_row,_payload,_cadence,_age_cache
    c=reassessment
    configure(c.life,monkeypatch,enabled=control!='off')
    if control=='weekend_positive':
        configure(c.life,monkeypatch,now=datetime(2026,11,13,22,tzinfo=UTC),start='2026-11-13',end='2026-11-16')
        c.life.provider.articles=(article(c.life,published=datetime(2026,11,13,21,30,tzinfo=UTC)),)
        c.life.service.get_news((CANDIDATE,),c.life.request,c.life.policy)
        c.life.clock.current=datetime(2026,11,14,14,40,tzinfo=UTC)
        for i in range(3):
            c.life.store.write({'JPM':(article(c.life,'W'+str(i),'JPM market bulletin',c.life.clock.current),)},
                NewsRequest(strategy_id='unrelated',max_evidence_per_symbol=1))
        c.life.clock.current=datetime(2026,11,16,14,40,tzinfo=UTC)
    now=c.life.clock.current
    calendar_receipt=receipt('2026-11-13','2026-11-16') if control=='weekend_positive' else receipt('2026-11-12','2026-11-13')
    facts=(article(c.life),)
    if control=='veto': facts=(*facts,article(c.life,'C','JPM announces registered direct offering',PUB-timedelta(days=1)))
    c.life.provider.articles=facts
    c.row['quote_timestamp_utc']=(now-timedelta(seconds=30)).isoformat()
    bundle=c.payload['ross_watchlist_reassessment'];bundle['date']=now.date().isoformat()
    payload=_payload([_row('JPM')],focus=[]);payload.update(c.payload)
    monkeypatch.setattr(core_module,'datetime',c.life.clock)
    core,scans,processed=_install_runtime_harness(monkeypatch,[payload])
    # The harness supplies an external stock/quote context, not session authority.
    monkeypatch.delenv('FORCE_SESSION',raising=False)
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,NEWS_ENABLED=True,
        NEWS_CACHE_FILE=str(c.life.store.cache_path),ROSS_ISSUER_QUERY_ENABLED=True,
        ROSS_NEXT_SESSION_CATALYST_ENABLED=control!='off',NEWS_MAX_ENTRIES_PER_SYMBOL=1,
        MARKET_SESSION_COVERAGE='' if control=='missing_calendar' else json.dumps(calendar_receipt),
        MARKET_HOLIDAYS=set(),MARKET_HALF_DAYS=set(),SESSION_PHASE_OVERRIDE=None))
    c.life.request=ross._ross_news_request()
    c.life.policy=ross._ross_retrieval_policy(refresh_mode='force_refresh',network_allowed=True)
    _,policy=core._build_scanner_policy_for_strategy('ross_momentum','RTH_OPEN')
    bundle['policy']=policy;bundle['thresholds']=ross._gate_thresholds(policy,ross._resolve_runtime_thresholds(policy,'RTH_OPEN'))
    core.connection_manager._client=object()
    c.provider.market_data_client=core.connection_manager.optional_client
    stub=core_module.run_scanner_cycle
    def scan(**kwargs):
        ross._PERSISTENT_PROVIDER=c.provider
        return stub(**kwargs)
    monkeypatch.setattr(core_module,'run_scanner_cycle',scan)
    core._news_maintenance=NS(read=lambda candidates,request,policy:
        c.life.service.get_news(candidates,request,replace(policy,network_allowed=False,
            refresh_mode='cache_only',allow_cache_write=False)),set_active=lambda *args:None)
    assert core.run_once() and _cadence(core).focus.symbols==[]
    if control!='weekend_positive':
        c.life.service.get_news((CANDIDATE,),c.life.request,c.life.policy)
    if control=='override': monkeypatch.setenv('FORCE_SESSION','RTH')
    before=c.life.store.cache_path.read_bytes() if c.life.store.cache_path.exists() else None
    _age_cache(_cadence(core).focus,11)
    assert core.run_once()
    expected=['JPM'] if control in {'positive','weekend_positive'} else []
    assert _cadence(core).focus.symbols==expected
    assert processed==([expected] if expected else []) and len(scans)==1
    assert (c.life.store.cache_path.read_bytes() if c.life.store.cache_path.exists() else None)==before
    assert c.life.provider.calls==1


@pytest.mark.parametrize('now,expected', [('2026-11-13T14:59:59.999999+00:00',True),('2026-11-13T15:00:00+00:00',False)])
def test_current_early_close_truncates_opening_window(lifecycle,monkeypatch,now,expected):
    from datetime import time as clocktime
    half={date(2026,11,13)}
    life=configure(lifecycle,monkeypatch,now=datetime.fromisoformat(now))
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,MARKET_HALF_DAYS=half,
        MARKET_EARLY_CLOSE_TIME=clocktime(10),
        MARKET_SESSION_COVERAGE=json.dumps(receipt('2026-11-12','2026-11-13',halves=half,early='10:00'))))
    life.request=ross._ross_news_request()
    assert decision(life,article(life))['qualified'] is expected


def test_missing_intervening_weekend_coverage_and_parameter_override_refuse(lifecycle,monkeypatch):
    now=datetime(2026,11,16,14,40,tzinfo=UTC)
    life=configure(lifecycle,monkeypatch,now=now,start='2026-11-13',end='2026-11-16')
    assert covered_opening_window(now)
    assert covered_opening_window(now,override_phase='PRE') is None
    data=receipt('2026-11-13','2026-11-16');del data['days']['2026-11-14']
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,MARKET_SESSION_COVERAGE=json.dumps(data)))
    assert covered_opening_window(now) is None


def test_changed_title_and_id_same_url_cannot_renew_original(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch)
    base=article(life,'B','JPM market bulletin',PUB-timedelta(days=1))
    update=replace(article(life,'NEW','JPM reports Q3 earnings beat',NOW-timedelta(seconds=1)),url=base.url)
    selected=retained_evidence((update,base),life.request)
    assert len(selected)==1 and selected[0].evidence_id=='B'
    assert selected[0].headline==base.headline and selected[0].published_at==base.published_at
    assert not decision(life,selected[0])['qualified']


def test_veto_survives_extra_expiry_stricter_cap_and_fresh_ordinary_positive(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch,limit=3)
    life.store.write({'JPM':pressure_facts(life)},life.request)
    life.clock.current=datetime(2026,11,13,15,30,tzinfo=UTC)
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES,NEWS_MAX_ENTRIES_PER_SYMBOL=1))
    life.request=ross._ross_news_request()
    fresh=article(life,'F','JPM reports Q3 earnings beat',life.clock.current)
    life.store.write({'JPM':(fresh,)},life.request)
    rows=life.store.read((CANDIDATE,),life.request).evidence_by_symbol['JPM']
    assert len(rows)<=4 and retained_dilution(rows)
    assert any(decision(life,row)['qualified'] for row in rows)
    life.provider.articles=()
    result=life.service.get_news((CANDIDATE,),life.request,replace(life.policy,network_allowed=False,refresh_mode='cache_only'))
    context=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert context['dilution_flag'] and not context['ross_catalyst_valid']


def test_other_strategy_cannot_inherit_acquisition_or_temporal_exception(lifecycle,monkeypatch):
    from src.news.news_intelligence_service import _acquisition_profile
    life=configure(lifecycle,monkeypatch)
    other=replace(life.request,strategy_id='unrelated')
    assert cp.next_session_publication_lower_bound(other,now_ts=NOW.timestamp()) is None
    profile=_acquisition_profile(CANDIDATE,other,life.policy,batch_candidates=(CANDIDATE,))
    assert 'next_session_calendar' not in profile['request']
    life.provider.articles=(article(life),)
    result=life.service.get_news((CANDIDATE,),other,life.policy)
    assert not ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['ross_catalyst_valid']
    if life.store.cache_path.exists():
        bucket=json.loads(life.store.cache_path.read_text())['news_intelligence']['symbols']['JPM']
        assert 'ross_retention_contract' not in bucket


def test_pre_to_open_rebinds_current_calendar_then_expires_at_end(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch,now=datetime(2026,11,13,14,29,59,900000,tzinfo=UTC))
    item=article(life)
    assert decision(life,item)['qualified']
    old_request=life.request
    life.clock.current=datetime(2026,11,13,14,30,tzinfo=UTC)
    assert decision(life,item)['qualified']  # Same immutable window; actual OPEN is independently re-evaluated.
    assert decision(life,item)['temporal_authority']['calendar']['phase']=='RTH_OPEN'
    life.request=ross._ross_news_request()
    assert decision(life,item)['qualified']
    assert life.request.metadata['next_session_calendar']!=old_request.metadata['next_session_calendar']
    life.clock.current=datetime(2026,11,13,15,30,tzinfo=UTC)
    assert not decision(life,item)['qualified']


def test_friday_positive_survives_closed_weekend_pressure_until_monday(lifecycle,monkeypatch):
    friday=datetime(2026,11,13,22,tzinfo=UTC)
    life=configure(lifecycle,monkeypatch,now=friday,start='2026-11-13',end='2026-11-16')
    positive=article(life,'B',published=datetime(2026,11,13,21,30,tzinfo=UTC))
    life.store.write({'JPM':(positive,)},life.request)
    life.clock.current=datetime(2026,11,14,14,40,tzinfo=UTC)
    candidate=cp.assess_issuer_event('JPM',positive,(CANDIDATE,),request=life.request,_retention_attribution=True)
    assert candidate['retention_candidate'] and candidate['qualified'] is False
    assert not decision(life,positive)['qualified']
    for i in range(3):
        generic=article(life,'W'+str(i),'JPM market bulletin',life.clock.current-timedelta(seconds=3-i))
        life.store.write({'JPM':(generic,)},NewsRequest(strategy_id='unrelated',max_evidence_per_symbol=1))
    life.clock.current=datetime(2026,11,16,14,40,tzinfo=UTC)
    life.request=ross._ross_news_request()
    rows=life.store.read((CANDIDATE,),life.request).evidence_by_symbol['JPM']
    assert any(row.evidence_id=='B' and decision(life,row)['qualified'] for row in rows)


def test_retained_raw_veto_flag_cannot_displace_independent_positive(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch)
    a,b,c,veto=pressure_facts(life)
    flagged=replace(article(life,'FLAG','JPM reports Q3 earnings beat',NOW-timedelta(minutes=1)),dilution_or_offering=True)
    selected=retained_evidence((a,b,flagged),life.request)
    assert any(row.evidence_id=='B' for row in selected) and retained_dilution(selected)
    assert cp.assess_issuer_event('JPM',flagged,request=life.request,_retention_attribution=True)['qualified'] is False


def test_unserializable_calendar_binding_refuses_only_additional_route(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch)
    life.request=replace(life.request,metadata={**life.request.metadata,'next_session_calendar':{'bad':object()}})
    assert not decision(life,article(life))['qualified']
    assert decision(life,article(life,published=NOW-timedelta(minutes=1)))['qualified']


@pytest.mark.parametrize('overlay',['prep','cache'])
@pytest.mark.parametrize('identity',['url','id'])
def test_intermediate_overlay_dedup_cannot_erase_headline_veto(lifecycle,monkeypatch,overlay,identity):
    from src.news.evidence_store import serialize_evidence
    life=configure(lifecycle,monkeypatch)
    base=article(life)
    life.store.write({'JPM':(base,)},life.request)
    observed=NOW-timedelta(minutes=5)
    update=article(life,'B' if identity=='id' else 'UPDATE','JPM announces registered direct offering',observed)
    update=replace(update,url=base.url if identity=='url' else 'https://fixture.invalid/different-version-url',
                   is_generic=True,dilution_or_offering=False)
    if overlay=='prep':
        life.store._prep_artifact_loader=lambda:{'symbols':[{'symbol':'JPM','news_context':[{
            'title':update.headline,'url':update.url,'evidence_id':update.evidence_id,
            'published_at':observed.isoformat(),'source':'fixture','catalyst_tag':'generic'}]}]}
    else:
        payload=json.loads(life.store.cache_path.read_text())
        payload['news_intelligence']['symbols']['JPM']['evidence'].append(serialize_evidence(update))
        life.store.cache_path.write_text(json.dumps(payload))  # Synthetic external persisted overlay.
    result=life.service.get_news((CANDIDATE,),life.request,replace(life.policy,network_allowed=False,refresh_mode='cache_only'))
    rows=result.evidence_for_symbol('JPM')
    assert retained_dilution(rows)
    auxiliary=next(row for row in rows if auxiliary_veto_version(row))
    assert auxiliary.published_at==base.published_at and auxiliary.stale
    assert original_publication_binding(auxiliary)['observed_published_ts']==observed.timestamp()
    context=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert context['dilution_flag'] and not context['ross_catalyst_valid']
    assert context['fresh_news_count']==0 and context['news_count']==1


@pytest.mark.parametrize('original_kind',['generic','old_earnings'])
def test_lifecycle_merged_identity_cannot_renew_newer_wrapper(lifecycle,monkeypatch,original_kind):
    life=configure(lifecycle,monkeypatch)
    newer=article(life,published=NOW-timedelta(minutes=1))
    life.provider.articles=(newer,)
    batch=life.service.get_news((CANDIDATE,),life.request,life.policy)
    handoff=ross._ross_news_contexts_from_news_intelligence_result(batch)['JPM']['catalyst_evidence']
    assert revalidate_handoff('JPM',handoff,store=life.store)['qualified']
    original=article(life,title='JPM market bulletin' if original_kind=='generic' else 'JPM reports Q3 earnings beat',
                     published=PUB-timedelta(days=1))
    life.store.write({'JPM':(original,)},life.request)
    current=life.store.read((CANDIDATE,),life.request).evidence_by_symbol['JPM']
    assert not any(decision(life,row)['qualified'] for row in current)
    assert not revalidate_handoff('JPM',handoff,store=life.store)['qualified']


@pytest.mark.parametrize('initial_title,later_title,expected',[
    ('JPM market bulletin','JPM reports Q3 earnings beat',False),
    ('JPM reports Q3 earnings beat','JPM market bulletin',True),
])
def test_equal_time_update_preserves_established_original(lifecycle,monkeypatch,initial_title,later_title,expected):
    life=configure(lifecycle,monkeypatch)
    original=article(life,'B',initial_title)
    update=replace(article(life,'A',later_title),url=original.url)
    life.store.write({'JPM':(original,)},life.request)
    life.store.write({'JPM':(update,)},life.request)
    rows=life.store.read((CANDIDATE,),life.request).evidence_by_symbol['JPM']
    assert len(rows)==1 and rows[0].headline==original.headline
    assert decision(life,rows[0])['qualified'] is expected


def test_unresolved_equal_time_content_conflict_never_grants_positive(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch)
    original=article(life,'B','JPM market bulletin')
    update=replace(article(life,'A','JPM reports Q3 earnings beat'),url=original.url)
    for rows in ((original,update),(update,original)):
        selected=retained_evidence(rows,life.request)
        assert not any(decision(life,row)['qualified'] for row in selected)


def test_retained_pre_handoff_survives_open_but_not_expiry_without_store(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch,now=datetime(2026,11,13,14,29,tzinfo=UTC))
    life.provider.articles=(article(life),)
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    handoff=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['catalyst_evidence']
    life.store.cache_path.unlink()  # Only the synthetic temporary canonical store.
    assert revalidate_handoff('JPM',handoff,store=life.store)['qualified']
    life.clock.current=datetime(2026,11,13,14,30,tzinfo=UTC)
    assert revalidate_handoff('JPM',handoff,store=life.store)['qualified']
    forged=deepcopy(handoff)
    for row in forged['temporal_bindings'].values(): row['calendar']['phase']='AH'
    assert not revalidate_handoff('JPM',forged,store=life.store)['qualified']
    life.clock.current=datetime(2026,11,13,15,30,tzinfo=UTC)
    assert not revalidate_handoff('JPM',handoff,store=life.store)['qualified']


def test_equal_time_offering_update_still_preserves_veto_against_known_positive(lifecycle,monkeypatch):
    life=configure(lifecycle,monkeypatch)
    positive=article(life,'B')
    veto=replace(article(life,'A','JPM announces registered direct offering'),url=positive.url)
    life.store.write({'JPM':(positive,)},life.request)
    life.store.write({'JPM':(veto,)},life.request)
    rows=life.store.read((CANDIDATE,),life.request).evidence_by_symbol['JPM']
    assert any(decision(life,row)['qualified'] for row in rows)
    assert retained_dilution(rows) and len(rows)==2


@pytest.mark.parametrize('boundary',['provider','handoff'])
def test_external_established_claim_cannot_override_legacy_canonical_original(lifecycle,monkeypatch,boundary):
    life=configure(lifecycle,monkeypatch,enabled=False)
    original=article(life,'B','JPM market bulletin')
    life.store.write({'JPM':(original,)},life.request)
    configure(life,monkeypatch,enabled=True)
    update=replace(article(life,'A'),url=original.url)
    update=replace(update,raw={**update.raw,'original_publication_binding':{
        'schema':'news.original_publication.v1','contract':cp.NEXT_SESSION_CONTRACT,'role':'base','established':True}})
    if boundary=='provider':
        life.provider.articles=(update,)
        batch=life.service.get_news((CANDIDATE,),life.request,life.policy)
        assert not ross._ross_news_contexts_from_news_intelligence_result(batch)['JPM']['ross_catalyst_valid']
        current=life.store.read((CANDIDATE,),life.request).evidence_by_symbol['JPM']
        assert current[0].headline==original.headline
    else:
        from src.strategies.ross_momentum.policy.catalyst_lifecycle import evidence_handoff
        handoff=evidence_handoff('JPM',(update,),CANDIDATE,acquisition_health='unknown',acquisition_reason='synthetic',request=life.request)
        assert not revalidate_handoff('JPM',handoff,store=life.store)['qualified']


@pytest.mark.parametrize('boundary', ['cache_read', 'generic_write', 'provider'])
def test_foreign_identity_cannot_coalesce_away_owned_veto(lifecycle, monkeypatch, boundary):
    from src.news.evidence_store import serialize_evidence
    life = configure(lifecycle, monkeypatch)
    positive = article(life, 'P')
    veto = article(life, 'V', 'JPM announces registered direct offering', NOW-timedelta(minutes=5))
    life.store.write({'JPM': (positive, veto)}, life.request)
    foreign = replace(article(life, 'FOREIGN', '$JPM.TO announces registered direct offering',
                              veto.published_at-timedelta(days=1)), url=veto.url)
    if boundary == 'provider':
        life.provider.articles = (foreign,)
        result = life.service.get_news((CANDIDATE,), life.request, life.policy)
        context = ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
        assert context['dilution_flag'] and not context['ross_catalyst_valid']
    else:
        payload = json.loads(life.store.cache_path.read_text())
        payload['news_intelligence']['symbols']['JPM']['evidence'].append(serialize_evidence(foreign))
        life.store.cache_path.write_text(json.dumps(payload))
        if boundary == 'generic_write':
            life.store.write({'JPM': (article(life, 'G', 'JPM market bulletin', NOW),)},
                             NewsRequest(strategy_id='unrelated', max_evidence_per_symbol=1))
    rows = life.store.read((CANDIDATE,), life.request).evidence_by_symbol['JPM']
    assert retained_dilution(rows)
    assert any(row.evidence_id == positive.evidence_id for row in rows)
    assert not any(row.evidence_id == foreign.evidence_id for row in rows)


@pytest.mark.parametrize('generic_issuer', [None, {'symbol': 'JPM', 'company_name': None, 'aliases': []},
    {'symbol': 'JPM', 'company_name': 'Unrelated Foreign Company', 'aliases': ['Foreign Company']}])
def test_company_name_only_veto_survives_repeated_generic_metadata_writes(lifecycle, monkeypatch, generic_issuer):
    life = configure(lifecycle, monkeypatch)
    positive = article(life, 'P')
    veto = replace(article(life, 'V', 'JPMorgan Chase announces registered direct offering', NOW),
                   company_name=None, aliases=())
    issuer = {'symbol': 'JPM', 'company_name': CANDIDATE.company_name, 'aliases': list(CANDIDATE.aliases)}
    life.store.write({'JPM': (positive, veto)}, life.request,
                     retrieval_by_symbol={'JPM': {'acquisition_profile': {'issuer': issuer}}})
    for index in range(3):
        life.store.write({'JPM': (article(life, str(index), 'JPM market bulletin', NOW),)},
                         NewsRequest(strategy_id='unrelated', max_evidence_per_symbol=1),
                         retrieval_by_symbol={'JPM': {'completed_at': NOW.isoformat(),
                             **({'acquisition_profile': {'issuer': generic_issuer}} if generic_issuer else {})}})
        rows = life.store.read((CANDIDATE,), life.request).evidence_by_symbol['JPM']
        assert retained_dilution(rows)
        assert any(row.evidence_id == veto.evidence_id for row in rows)


@pytest.mark.parametrize('invalid_marker', [None, {}, [], '', 0, {'contract': 'unknown'},
    {'contract': cp.NEXT_SESSION_CONTRACT, 'presentation_limit': True}])
def test_unknown_protected_retention_marker_refuses_write_without_mutating_cache(lifecycle, monkeypatch, invalid_marker):
    life = configure(lifecycle, monkeypatch)
    life.store.write({'JPM': (article(life),)}, life.request)
    payload = json.loads(life.store.cache_path.read_text())
    payload['news_intelligence']['symbols']['JPM']['ross_retention_contract'] = invalid_marker
    life.store.cache_path.write_text(json.dumps(payload))
    before = life.store.cache_path.read_bytes()
    result = life.store.write({'JPM': (article(life, 'G', 'JPM market bulletin', NOW),)}, life.request)
    assert result['cache_write_failed'] and result['cache_write_error'] == 'protected_retention_marker_invalid'
    assert life.store.cache_path.read_bytes() == before


@pytest.mark.parametrize('invalid_issuer', [None, {'symbol': 'OTHER'},
    {'symbol': 'OTHER', 'company_name': None, 'aliases': []},
    {'symbol': 'JPM', 'company_name': ['unexpected'], 'aliases': []},
    {'symbol': 'JPM', 'company_name': None, 'aliases': 'unexpected'},
    {'symbol': 'JPM', 'company_name': None, 'aliases': [None]}])
def test_malformed_protected_issuer_refuses_destructive_generic_write(lifecycle, monkeypatch, invalid_issuer):
    life = configure(lifecycle, monkeypatch)
    veto = replace(article(life, 'V', 'JPMorgan Chase announces registered direct offering', NOW),
                   company_name=None, aliases=())
    issuer = {'symbol': 'JPM', 'company_name': CANDIDATE.company_name, 'aliases': list(CANDIDATE.aliases)}
    life.store.write({'JPM': (article(life), veto)}, life.request,
                     retrieval_by_symbol={'JPM': {'acquisition_profile': {'issuer': issuer}}})
    payload = json.loads(life.store.cache_path.read_text())
    payload['news_intelligence']['symbols']['JPM']['ross_retention_contract']['issuer'] = invalid_issuer
    life.store.cache_path.write_text(json.dumps(payload))
    before = life.store.cache_path.read_bytes()
    result = life.store.write({'JPM': (article(life, 'G', 'JPM market bulletin', NOW),)},
                              NewsRequest(strategy_id='unrelated', max_evidence_per_symbol=1))
    assert result['cache_write_failed'] and result['cache_write_error'] == 'protected_retention_marker_invalid'
    assert life.store.cache_path.read_bytes() == before


@pytest.mark.parametrize('marker', [None, {}, [], {'contract': 'unknown'},
    {'contract': cp.NEXT_SESSION_CONTRACT, 'presentation_limit': 0},
    {'contract': cp.NEXT_SESSION_CONTRACT, 'presentation_limit': 1, 'issuer': {'symbol': 'OTHER'}}])
@pytest.mark.parametrize('refresh', [False, True])
def test_unsupported_marker_cannot_hide_retained_veto_after_disable(lifecycle, monkeypatch, marker, refresh):
    life = configure(lifecycle, monkeypatch)
    veto = article(life, 'V', 'JPM announces registered direct offering', NOW-timedelta(days=2))
    positive = article(life, 'P', published=NOW-timedelta(minutes=1))
    life.store.write({'JPM': (positive, veto)}, life.request)
    payload = json.loads(life.store.cache_path.read_text())
    payload['news_intelligence']['symbols']['JPM']['ross_retention_contract'] = marker
    life.store.cache_path.write_text(json.dumps(payload))
    cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, ROSS_NEXT_SESSION_CATALYST_ENABLED=False))
    life.request = ross._ross_news_request()
    foreign = replace(article(life, 'FOREIGN', '$JPM.TO announces registered direct offering',
                              veto.published_at-timedelta(days=1)), url=veto.url)
    life.provider.articles = (positive, foreign)
    policy = life.policy if refresh else replace(life.policy, network_allowed=False, refresh_mode='cache_only', allow_cache_write=False)
    result = life.service.get_news((CANDIDATE,), life.request, policy)
    context = ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert context['dilution_flag'] and not context['ross_catalyst_valid']
    assert retained_dilution(result.evidence_by_symbol['JPM'])
    assert not any(row.evidence_id == foreign.evidence_id for row in result.evidence_by_symbol['JPM'])


def test_phase_only_transition_preserves_source_profile_and_real_acquisition_cadence(lifecycle, monkeypatch):
    from src.news.news_intelligence_service import _acquisition_profile
    life = configure(lifecycle, monkeypatch, now=datetime(2026,11,13,14,29,59,tzinfo=UTC))
    life.policy = replace(life.policy, refresh_mode='bounded_refresh', refresh_interval_seconds=120)
    before = _acquisition_profile(CANDIDATE, life.request, life.policy, batch_candidates=(CANDIDATE,))
    life.provider.articles = (article(life),)
    first = life.service.get_news((CANDIDATE,), life.request, life.policy)
    assert life.provider.calls == 1
    assert ross._ross_news_contexts_from_news_intelligence_result(first)['JPM']['ross_catalyst_valid']
    life.clock.current = datetime(2026,11,13,14,30,tzinfo=UTC)
    life.request = ross._ross_news_request()
    after = _acquisition_profile(CANDIDATE, life.request, life.policy, batch_candidates=(CANDIDATE,))
    assert before == after
    assert life.request.metadata['next_session_calendar']['phase'] == 'RTH_OPEN'
    second = life.service.get_news((CANDIDATE,), life.request, life.policy)
    assert life.provider.calls == 1
    assert ross._ross_news_contexts_from_news_intelligence_result(second)['JPM']['ross_catalyst_valid']
    life.clock.current = datetime(2026,11,13,15,30,tzinfo=UTC)
    life.request = ross._ross_news_request()
    assert _acquisition_profile(CANDIDATE, life.request, life.policy, batch_candidates=(CANDIDATE,)) != before
    assert not decision(life, article(life))['qualified']
