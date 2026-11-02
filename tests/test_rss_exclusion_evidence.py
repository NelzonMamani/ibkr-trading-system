"""Controlled response replay: unchanged freshness/matching and bounded diagnostics."""
from datetime import datetime, timezone
from dataclasses import replace
from email.utils import formatdate
import json
import time
import pytest
from types import SimpleNamespace as NS

from src.news import news_fetcher as fetcher
from src.news.rss_exclusion_evidence import retain_exclusion


def test_old_first_feed_does_not_hide_fresh_tail_and_retains_rejection(monkeypatch):
    now=time.time()
    def item(title, age=60, **kwargs):
        return NS(title=title,link='https://fixture.invalid/article',summary='Original issuer summary',
                  published_parsed=time.gmtime(now-age),published=formatdate(now-age,usegmt=True),**kwargs)
    entries=[item('Old CLIK earnings',age=90000) for _ in range(20)]
    entries += [item('Unrelated current issuer event'),item('CLIK reports earnings beat')]
    url='https://fixture.invalid/issuer'
    monkeypatch.setattr(fetcher,'_fetch_feed',lambda *args:NS(version="rss20", bozo=False, entries=entries,feed={'title':'Fixture'}))
    from src.strategies.ross_momentum.policy.catalyst_policy import select_qualification_evidence
    from src.news.news_intelligence_contract import NewsRequest
    rows,summary=fetcher.fetch_headlines_for_symbols(['CLIK'],[url],lookback_hours=6,
        source_tier='operational_query',source_groups_by_url={url:'ROSS_ISSUER_QUERY'},
        max_entries_per_symbol=1,retention_selector=select_qualification_evidence,
        retention_request=NewsRequest(max_evidence_per_symbol=1,metadata={'presentation_limit':1}),symbol_metadata={'CLIK':{'company_name':'Click Holdings'}})
    assert len(rows['CLIK'])==1 and rows['CLIK'][0].title=='CLIK reports earnings beat'
    d=summary.source_diagnostics[0]['entry_diagnostics']
    assert d['stale_entries']==20 and d['within_window']==2
    assert summary.source_diagnostics[0]['entries_examined_count']==22
    e=d['exclusion_evidence']
    assert e['counts']=={'outside_lookback_window':20,'issuer_match_unverified':1}
    assert len(e['samples']['outside_lookback_window'])==2
    rejected=e['samples']['issuer_match_unverified'][0]
    assert rejected['entry_index']==21 and rejected['symbol']=='CLIK'
    assert rejected['title']=='Unrelated current issuer event'
    assert rejected['summary']=='Original issuer summary' and rejected['identity_patterns']
    assert rejected['timestamp_provenance']['selected_time_basis']=='published'
    assert not rejected['title_truncated'] and not rejected['privacy_redacted']


def test_sample_bounds_and_existing_privacy_workflow(tmp_path):
    from src.ibkr.evidence_safety import write_json,scan_artifacts
    d={}
    for i in range(100):
        retain_exclusion(d,reason='issuer_match_unverified',entry_index=i,title='DU1234567 '+'x'*10000,
            summary='x'*20000,url='https://fixture.invalid/'+'x'*5000,
            date_facts={'published_original':'x'*5000},symbol='CLIK',identity_patterns=('x'*5000,)*10)
    e=d['exclusion_evidence'];samples=e['samples']['issuer_match_unverified']
    assert e['counts']['issuer_match_unverified']==100 and len(samples)==2
    assert samples[0]['title_truncated'] and samples[0]['summary_truncated']
    assert samples[0]['privacy_redacted'] and samples[0]['identity_patterns_truncated']
    assert samples[0]['timestamp_provenance_truncated']
    assert 'DU1234567' not in json.dumps(d)
    assert len(json.dumps(d))<15000
    write_json(tmp_path/'exclusions.json',d)
    assert scan_artifacts(tmp_path)['passed']


def test_timezone_publication_precedes_updated_and_original_window_unchanged():
    import feedparser
    feed=feedparser.parse('''<rss version="2.0"><channel><title>Fixture</title><item><title>CLIK reports earnings</title>
      <pubDate>Thu, 22 Oct 2026 12:00:00 -0400</pubDate></item></channel></rss>''')
    entry=feed.entries[0]
    entry['updated_parsed']=time.gmtime(datetime(2026,10,22,19,tzinfo=timezone.utc).timestamp())
    stamp,facts=fetcher._entry_date_facts(entry)
    assert stamp==datetime(2026,10,22,16,tzinfo=timezone.utc).timestamp()
    assert facts['selected_time_basis']=='published' and facts['published_utc'].endswith('16:00:00+00:00')


def test_exclusion_survives_canonical_metadata_without_becoming_news(monkeypatch,tmp_path,capsys):
    from src.config.config_resolver import set_config_overrides
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
    from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
    from src.news.news_intelligence_contract import NewsCandidate
    from src.scanner import scanner_runner as ross
    from src.news.rss_lifecycle import RssFetchLifecycle
    lifecycle=RssFetchLifecycle()
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':True,'NEWS_ENABLED':True})
    try:
        entry=NS(title='Unrelated fresh article',summary='Bounded original summary',link='https://fixture.invalid/a',
                 published_parsed=time.gmtime(time.time()-60))
        monkeypatch.setattr(fetcher,'_fetch_feed',lambda url,*args:NS(version="rss20", bozo=False,
            entries=[entry] if 'news.google.com' in url else [],feed={'title':'Fixture'}))
        store=CanonicalNewsEvidenceStore(tmp_path/'news.json',prep_artifact_loader=lambda:{})
        service=CanonicalNewsIntelligenceService(evidence_store=store,retrieval_provider=BatchRssNewsIntelligenceProvider(lifecycle=lifecycle))
        result=service.get_news((NewsCandidate('CLIK',company_name='Click Holdings'),),ross._ross_news_request(),
            ross._ross_retrieval_policy(refresh_mode='force_refresh',network_allowed=True))
        assert not result.evidence_for_symbol('CLIK')
        bucket=json.loads(store.cache_path.read_text())['news_intelligence']['symbols']['CLIK']
        sources=bucket['last_retrieval']['coverage']['diagnostics']['source_diagnostics']
        captured=[s['entry_diagnostics']['exclusion_evidence'] for s in sources
                  if 'exclusion_evidence' in s.get('entry_diagnostics',{})]
        assert len(captured)==1
        assert captured[0]['samples']['issuer_match_unverified'][0]['title']=='Unrelated fresh article'
        stdout = capsys.readouterr().out
        assert 'Unrelated fresh article' not in stdout  # stdout stays content-free
        event = json.loads(next(line.split('] ', 1)[1] for line in stdout.splitlines()
                                if line.startswith('[NEWS][RETRIEVAL_DIAGNOSTICS] ')))
        counts = event['entry_counts']
        # Query row must survive the byte budget even after fixed source rows.
        query = next(row for row in counts['rows'] if
                     event['sources'][row['source_index']]['source_group']=='ROSS_ISSUER_QUERY')
        assert query['parser_entries']==query['entries_examined']==1
        assert query['reason_counts']['issuer_match_unverified']==1
        assert query['issuer_rejections']==[{'symbol_index':0,'count':1}]
        assert query['traversal_scope']=='all_parser_entries'
        assert counts['qualification_evaluated'] is False
    finally:
        assert lifecycle.wait_for_cleanup(2)['cleanup_complete']
        set_config_overrides({})


def test_full_sample_slots_do_not_process_more_excluded_summary_text():
    calls=[]
    d={}
    for index in range(100):
        retain_exclusion(d,reason='outside_lookback_window',entry_index=index,title='old',
            summary=lambda:calls.append(True) or 'summary',url='',date_facts={})
    assert len(calls)==2
    assert d['exclusion_evidence']['counts']['outside_lookback_window']==100


def test_privacy_expansion_sets_truncation_flag_at_exact_boundary():
    d={}
    title='x'*505+' U12345'
    assert len(title)==512
    retain_exclusion(d,reason='issuer_match_unverified',entry_index=1,title=title,
                     summary='',url='',date_facts={})
    row=d['exclusion_evidence']['samples']['issuer_match_unverified'][0]
    assert len(row['title'])==512 and row['privacy_redacted'] and row['title_truncated']
    assert 'U12345' not in row['title']


# Per-result reporting controls. All transports above remain synthetic; these
# fixtures pass already-produced measurements directly to the existing emitter.
def _measured_source(**changes):
    from src.news.news_intelligence_contract import ResearchSourceDiagnostic
    values = dict(source_id='https://fixture.invalid/feed', source_group='ROSS_ISSUER_QUERY',
        source_tier='operational_query', retrieval_status='available', attempted=True,
        worker_completed=True, response_closed=True, http_status=200,
        feed_item_count=5, entries_examined_count=5, matched_count=1,
        entry_diagnostics={
            'usable_dates':4,'within_window':2,'missing_invalid_dates':1,
            'stale_entries':1,'future_entries':1,'missing_titles':0,
            'published_time_used':4,'updated_time_used':0,
            'evaluation_time_utc':'2026-11-02T19:55:00+00:00',
            'relevance_rejections_by_symbol':{'CLIK':1},
            'exclusion_evidence':{'schema':'news.rss_exclusions.v1','counts':{
                'outside_lookback_window':1,'future_publication_time':1,
                'missing_publication_time':1,'issuer_match_unverified':1}}})
    values.update(changes)
    return ResearchSourceDiagnostic(**values)


def _count_result(sources, symbols=('CLIK',)):
    from src.news.news_intelligence_contract import NewsBatchResult,NewsCandidate,RetrievalDiagnostics
    return NewsBatchResult(candidates=tuple(NewsCandidate(s) for s in symbols),
        diagnostics=RetrievalDiagnostics(source_diagnostics=tuple(sources)))


def _emit_counts(result,capsys,invoked=True):
    from src.news.retrieval_diagnostics import emit_retrieval_diagnostics
    emit_retrieval_diagnostics(result,provider_invoked=invoked)
    return json.loads(capsys.readouterr().out.split('[NEWS][RETRIEVAL_DIAGNOSTICS] ')[-1])


def test_result_projection_preserves_measured_counts_and_original_result(capsys):
    from dataclasses import asdict
    result=_count_result([_measured_source()]); before=asdict(result)
    event=_emit_counts(result,capsys);projection=event['entry_counts']; row=projection['rows'][0]
    assert row['parser_entries']==5 and row['entries_examined']==5 and row['matched_count']==1
    assert row['date_counts']['stale_entries']==1 and row['date_counts']['missing_invalid_dates']==1
    assert row['reason_counts']['issuer_match_unverified']==1
    assert row['reason_counts']['missing_title'] is None  # never fabricate an absent key as0
    assert row['date_counts_scope']=='all_parser_entries'
    assert row['issuer_rejections_scope']=='compared_time_valid_entries'
    assert row['duplicate_exclusions'] is row['classification_exclusions'] is None
    assert projection['qualification_evaluated'] is False
    assert asdict(result)==before


def test_empty_failure_partial_and_unknown_have_distinct_count_scope(capsys):
    from src.news.news_intelligence_contract import SourceDiagnostic
    rows=[_measured_source(feed_item_count=0,entries_examined_count=0,matched_count=0,
                          entry_diagnostics={key:0 for key in ('usable_dates','within_window',
                          'missing_invalid_dates','stale_entries','future_entries','missing_titles',
                          'published_time_used','updated_time_used')}),
          _measured_source(feed_item_count=20,entries_examined_count=5,processing_truncated=True,
                           retrieval_status='partial',budget_exhausted=True),
          _measured_source(worker_completed=False,entries_examined_count=None,feed_item_count=None,
                           retrieval_status='budget_exhausted',budget_exhausted=True,entry_diagnostics={}),
          SourceDiagnostic('https://fixture.invalid/error',retrieval_status='provider_error',
                           failure_reason='HTTP_403',worker_completed=True,http_status=403),
          SourceDiagnostic('https://fixture.invalid/unattempted',retrieval_status='not_requested',
                           failure_reason='deadline_exhausted_before_attempt')]
    event=_emit_counts(_count_result(rows),capsys)
    by_index={r['source_index']:r for r in event['entry_counts']['rows']}
    assert by_index[0]['parser_entries']==0 and by_index[0]['date_counts_scope']=='all_parser_entries'
    assert by_index[1]['traversal_scope']=='examined_prefix'
    for i in (2,3,4):
        assert by_index[i]['traversal_scope']=='unknown'
        assert by_index[i]['matched_count'] is None
        assert by_index[i]['parser_entries'] is None
    assert event['sources'][1]['budget_exhausted'] and event['sources'][2]['worker_completed'] is False
    assert event['sources'][3]['http_status']==403
    assert event['sources'][4]['failure_code']=='deadline_exhausted_before_attempt'


def test_cached_counts_are_not_new_fetch_and_missing_send_flag_is_unknown(capsys):
    from src.news.retrieval_diagnostics import _entry_counts_projection
    source=_measured_source(entry_diagnostics={'http_request_attempted':False})
    row=_entry_counts_projection(_count_result([source]),True)['rows'][0]
    assert row['http_request_attempted'] is None
    reused=_measured_source(entry_diagnostics={'transport_cache_hit':True,'http_request_attempted':False})
    assert _entry_counts_projection(_count_result([reused]),True)['rows'][0]['transport_cache_hit'] is True
    event=_emit_counts(_count_result([source]),capsys,invoked=False)
    assert event['entry_counts']['status']=='not_collected_this_result'
    assert event['entry_counts']['rows']==[] and event['entry_counts']['sources_omitted']==1


def test_row_and_byte_limits_are_independent_and_omissions_are_honest():
    from src.news.retrieval_diagnostics import _entry_counts_projection,_entry_projection_bytes
    result=_count_result([_measured_source() for _ in range(40)])
    projection=_entry_counts_projection(result,True)
    assert len(projection['rows'])<=24 and _entry_projection_bytes(projection)<=8192
    assert projection['omissions']['row_limit']==16
    assert projection['sources_omitted']==40-len(projection['rows'])
    assert projection['omissions']['byte_limit']>0
    assert projection['truncated'] and projection['status']=='partial_projection'
    assert projection['omitted_bytes'] is None


def test_exact_byte_boundary_includes_final_metadata(monkeypatch):
    from src.news import retrieval_diagnostics as diag
    result=_count_result([_measured_source()])
    monkeypatch.setattr(diag,'_entry_row',lambda *args:{'source_index':0,'padding':''})
    size=diag._entry_projection_bytes(diag._entry_counts_projection(result,True))
    padding='x'*(8192-size)
    monkeypatch.setattr(diag,'_entry_row',lambda *args:{'source_index':0,'padding':padding})
    exact=diag._entry_counts_projection(result,True)
    assert len(exact['rows'])==1 and diag._entry_projection_bytes(exact)==8192
    monkeypatch.setattr(diag,'_entry_row',lambda *args:{'source_index':0,'padding':padding+'x'})
    overflow=diag._entry_counts_projection(result,True)
    assert not overflow['rows'] and overflow['omissions']['byte_limit']==1
    assert diag._entry_projection_bytes(overflow)<=8192


def test_projection_ignores_private_objects_and_bad_counts(capsys,tmp_path):
    from src.ibkr.evidence_safety import write_json,scan_artifacts
    class Private:
        def __str__(self):raise AssertionError('Must never stringify private data')
    raw={'title':'DU1234567 secret article','summary':'private body','query':'private query',
         'hash':'private hash','exception':Private(),'account':Private(),
         'stale_entries':True,'future_entries':float('nan'),'within_window':-1,
         'missing_titles':2**100000,'usable_dates':'DU1234567',
         'evaluation_time_utc':'2026-11-02 DU1234567','relevance_rejections_by_symbol':{'CLIK':Private(),'DU1234567':9},
         'exclusion_evidence':{'schema':'news.rss_exclusions.v1','counts':{'outside_lookback_window':Private()},
                               'samples':Private()}}
    event=_emit_counts(_count_result([_measured_source(entry_diagnostics=raw)]),capsys)
    row=event['entry_counts']['rows'][0]
    assert row['date_counts'] is None and row['issuer_rejections'] is None
    assert row['utc_facts'] is None and row['reason_counts'] is None
    text=json.dumps(event['entry_counts'])
    assert not any(word in text for word in ('DU1234567','secret article','private body','private query','private hash'))
    write_json(tmp_path/'projection.json',event['entry_counts']);assert scan_artifacts(tmp_path)['passed']


def test_projection_failure_is_visible_without_mutating_outcome(monkeypatch,capsys):
    from dataclasses import asdict
    from src.news import retrieval_diagnostics as diag
    result=_count_result([_measured_source()]);before=asdict(result)
    def broken(*args):raise ValueError('private exception DU1234567')
    monkeypatch.setattr(diag,'_entry_counts_projection',broken)
    event=_emit_counts(result,capsys)
    assert event['entry_counts']['status']=='projection_error' and event['entry_counts']['truncated']
    assert 'DU1234567' not in json.dumps(event)
    assert event['sources'][0]['matched_count']==1 and asdict(result)==before


def test_two_real_service_results_keep_old_exclusions_after_latest_cache_changes(monkeypatch,tmp_path,capsys):
    from src.config.config_resolver import set_config_overrides
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
    from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
    from src.news.news_intelligence_contract import NewsCandidate
    from src.news.rss_lifecycle import RssFetchLifecycle
    from src.scanner import scanner_runner as ross
    now=time.time();calls=[]
    matched=NS(title='CLIK reports earnings beat',link='https://fixture.invalid/a',
               summary='synthetic issuer event',published_parsed=time.gmtime(now-60))
    unrelated=NS(title='Another issuer',link='https://fixture.invalid/b',
                 published_parsed=time.gmtime(now-60))
    entries=[matched,matched,unrelated]
    def feed(url,*args):
        calls.append(url)
        return NS(version='rss20',bozo=False,entries=list(entries) if 'news.google.com' in url else [],feed={})
    monkeypatch.setattr(fetcher,'_fetch_feed',feed)
    lifecycle=RssFetchLifecycle()
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':True,'NEWS_ENABLED':True})
    try:
        store=CanonicalNewsEvidenceStore(tmp_path/'news.json',prep_artifact_loader=lambda:{})
        service=CanonicalNewsIntelligenceService(evidence_store=store,
            retrieval_provider=BatchRssNewsIntelligenceProvider(lifecycle=lifecycle))
        candidate=(NewsCandidate('CLIK',company_name='Click Holdings'),)
        request=ross._ross_news_request()
        policy=ross._ross_retrieval_policy(refresh_mode='force_refresh',network_allowed=True)
        first=service.get_news(candidate,request,policy)
        first_log=capsys.readouterr().out
        entries.clear()
        second=service.get_news(candidate,request,policy)
        second_log=capsys.readouterr().out
        def query(log):
            event=json.loads(next(line.split('] ',1)[1] for line in log.splitlines()
                                 if line.startswith('[NEWS][RETRIEVAL_DIAGNOSTICS] ')))
            return next(row for row in event['entry_counts']['rows'] if
                        event['sources'][row['source_index']]['source_group']=='ROSS_ISSUER_QUERY')
        a=query(first_log);b=query(second_log)
        assert a['parser_entries']==a['entries_examined']==3 and a['matched_count']==1
        assert a['reason_counts']['issuer_match_unverified']==1
        assert a['duplicate_exclusions'] is None  # actual duplicate skip remains unmeasured
        assert b['parser_entries']==0 and b['entries_examined']==0
        assert b['reason_counts'] is None and b['traversal_scope']=='all_parser_entries'
        assert len(first.evidence_for_symbol('CLIK'))==len(second.evidence_for_symbol('CLIK'))==1
        assert a==query(first_log)  # not replaced by later empty-result coverage
        latest=json.loads(store.cache_path.read_text())['news_intelligence']['symbols']['CLIK']
        query_sources=[s for s in latest['last_retrieval']['coverage']['source_diagnostics']
                       if s['source_group']=='ROSS_ISSUER_QUERY']
        assert query_sources[0]['feed_item_count']==0
        assert sum('news.google.com' in url for url in calls)==2
    finally:
        assert lifecycle.wait_for_cleanup(2)['cleanup_complete']
        set_config_overrides({})


def test_historical_btoc_shape_stays_unknown_and_segg_classification_unchanged(monkeypatch,capsys):
    from src.news.news_intelligence_contract import NewsEvidence,NewsCandidate
    from src.strategies.ross_momentum.policy import catalyst_policy as policy
    # Historical flattened rows had22 parser entries but no examined/reason data.
    event=_emit_counts(_count_result([_measured_source(feed_item_count=22,
                        entries_examined_count=None,matched_count=0,entry_diagnostics={})],('BTOC',)),capsys)
    row=event['entry_counts']['rows'][0]
    assert event['sources'][0]['matched_count']==0
    assert row['parser_entries']==22 and row['matched_count'] is None
    assert row['date_counts'] is None and row['reason_counts'] is None
    assert row['traversal_scope']=='unknown'
    clock=datetime(2026,11,2,19,57,58,tzinfo=timezone.utc)
    monkeypatch.setattr(time,'time',lambda:clock.timestamp())
    article=NewsEvidence(symbol='SEGG',headline='Sports Entertainment Gaming Shares Rise After Q2 Loss Narrows, Revenue Rises',
                         published_at=datetime(2026,11,2,18,6,17,tzinfo=timezone.utc),
                         company_name='SPORTS ENTERTAINMENT GAMING',source_tier='operational_query')
    decision=policy.assess_issuer_event('SEGG',article,(NewsCandidate('SEGG',company_name=article.company_name),))
    assert decision['reason']=='no_catalyst_classification' and not decision['qualified']
    def forbidden(*args,**kwargs):raise AssertionError('Reporting must not call classifier')
    monkeypatch.setattr(policy,'assess_issuer_event',forbidden)
    _emit_counts(_count_result([_measured_source()]),capsys)


def test_interleaved_issuer_rows_use_indices_without_cross_inheritance(capsys):
    first=_emit_counts(_count_result([_measured_source()],('CLIK','OTHER')),capsys)
    second=_emit_counts(_count_result([_measured_source(entry_diagnostics={
        'relevance_rejections_by_symbol':{'OTHER':7,'CLIK':99}})],('OTHER',)),capsys)
    assert first['entry_counts']['rows'][0]['issuer_rejections']==[
        {'symbol_index':0,'count':1},{'symbol_index':1,'count':None}]
    assert second['entry_counts']['rows'][0]['issuer_rejections']==[{'symbol_index':0,'count':7}]


def test_missing_completion_is_not_exhaustive_and_each_metric_keeps_unknowns():
    from src.news.retrieval_diagnostics import _entry_counts_projection
    from dataclasses import replace
    base=_measured_source()
    for source in (replace(base,worker_completed=None),replace(base,processing_truncated=None)):
        row=_entry_counts_projection(_count_result([source]),True)['rows'][0]
        assert row['traversal_scope']==row['date_counts_scope']=='unknown'
        assert row['reason_counts_traversal_scope']=='unknown'
    row=_entry_counts_projection(_count_result([replace(base,processing_truncated=True,
                         retrieval_status='partial',entries_examined_count=3)]),True)['rows'][0]
    assert row['reason_counts_traversal_scope']==row['issuer_rejections_traversal_scope']=='examined_prefix'


def test_projection_reads_no_more_than24_sources_or50_current_symbols(monkeypatch):
    from src.news import retrieval_diagnostics as diag
    touched=[];original=diag._entry_row
    def measured(item,index,symbols):
        touched.append(index);return original(item,index,symbols)
    monkeypatch.setattr(diag,'_entry_row',measured)
    result=_count_result([_measured_source() for _ in range(60)],tuple('T'+str(i) for i in range(60)))
    projection=diag._entry_counts_projection(result,True)
    assert touched==list(range(24))
    assert projection['symbol_counts_omitted']==10 and projection['truncated']
    assert diag._entry_projection_bytes(projection)<=8192


def test_non_dictionary_measurements_are_unknown_without_invoking_custom_access():
    from collections.abc import Mapping
    from src.news.retrieval_diagnostics import _entry_counts_projection
    class PrivateMapping(Mapping):
        def __getitem__(self,key):raise AssertionError('Unexpected measurement access')
        def __iter__(self):raise AssertionError('Unexpected measurement enumeration')
        def __len__(self):raise AssertionError('Unexpected measurement sizing')
    projection=_entry_counts_projection(_count_result([_measured_source(entry_diagnostics=PrivateMapping())]),True)
    assert projection['rows'][0]['date_counts'] is None
    assert projection['rows'][0]['reason_counts'] is None


def test_inconsistent_date_measurement_cannot_claim_exhaustive_date_counts():
    from src.news.retrieval_diagnostics import _entry_counts_projection
    source=_measured_source()
    source.entry_diagnostics['within_window']=999
    row=_entry_counts_projection(_count_result([source]),True)['rows'][0]
    assert row['date_counts']['within_window']==999  # preserve reported fact, no clamping
    assert row['date_counts_scope']=='unknown'


# Additional exact-head review controls: units and cross-facet consistency.


@pytest.mark.parametrize('tier,expected,scope',[
    ('research',2,'before_duplicate_and_article_cap_filtering'),
    ('operational_query',1,'after_duplicate_skip_before_retention'),
])
def test_review_match_counter_scope_follows_actual_fetcher_mode(monkeypatch,tier,expected,scope):
    from src.news.batch_rss_adapter import _source_diagnostics_from_summary
    from src.news.retrieval_diagnostics import _entry_counts_projection
    from src.news.news_intelligence_contract import NewsRequest
    from src.strategies.ross_momentum.policy.catalyst_policy import select_qualification_evidence
    entry=NS(title='CLIK reports earnings beat',link='https://fixture.invalid/a',
             published_parsed=time.gmtime(time.time()-60))
    monkeypatch.setattr(fetcher,'_fetch_feed',lambda *args:NS(version='rss20',bozo=False,
        entries=[entry,entry],feed={}))
    url='https://fixture.invalid/feed'
    articles,summary=fetcher.fetch_headlines_for_symbols(['CLIK'],[url],lookback_hours=6,
        source_tier=tier,source_groups_by_url={url:'ROSS_ISSUER_QUERY'},
        retention_selector=select_qualification_evidence,
        retention_request=NewsRequest(max_evidence_per_symbol=5,metadata={'presentation_limit':5}),
        symbol_metadata={'CLIK':{'company_name':'Click Holdings'}})
    assert len(articles['CLIK'])==1
    row=_entry_counts_projection(_count_result(_source_diagnostics_from_summary(summary)),True)['rows'][0]
    assert row['matched_count']==expected
    assert row['matched_count_scope']==scope
    assert row['matched_count_units']=='entry_symbol_match_observations'
    assert row['duplicate_exclusions'] is None


def test_review_multiissuer_rejections_are_comparisons_not_unique_articles(monkeypatch):
    from src.news.batch_rss_adapter import _source_diagnostics_from_summary
    from src.news.retrieval_diagnostics import _entry_counts_projection
    from src.news.news_intelligence_contract import NewsRequest
    from src.strategies.ross_momentum.policy.catalyst_policy import select_qualification_evidence
    entry=NS(title='Different company reports earnings',link='https://fixture.invalid/a',
             published_parsed=time.gmtime(time.time()-60))
    monkeypatch.setattr(fetcher,'_fetch_feed',lambda *args:NS(version='rss20',bozo=False,entries=[entry],feed={}))
    url='https://fixture.invalid/feed'
    _,summary=fetcher.fetch_headlines_for_symbols(['CLIK','OTHER'],[url],lookback_hours=6,
        source_tier='operational_query',source_groups_by_url={url:'ROSS_ISSUER_QUERY'},
        retention_selector=select_qualification_evidence,retention_request=NewsRequest(),
        symbol_metadata={'CLIK':{'company_name':'Click Holdings'},'OTHER':{'company_name':'Other Issuer'}})
    sources=tuple(replace(source,source_group='ROSS_ISSUER_QUERY')
                  for source in _source_diagnostics_from_summary(summary))
    row=_entry_counts_projection(_count_result(sources,('CLIK','OTHER')),True)['rows'][0]
    assert row['entries_examined']==1 and row['reason_counts']['issuer_match_unverified']==2
    assert [x['count'] for x in row['issuer_rejections']]==[1,1]
    assert row['reason_count_units']['issuer_match_unverified']=='entry_symbol_rejection_observations'
    assert row['reason_count_units']['missing_title']=='entry_rejection_observations'


def test_review_contradictory_date_partitions_do_not_certify_exhaustive_scope():
    from src.news.retrieval_diagnostics import _entry_counts_projection
    source=_measured_source()
    source.entry_diagnostics['missing_invalid_dates']=0  # four usable+zero missing !=five examined
    row=_entry_counts_projection(_count_result([source]),True)['rows'][0]
    assert row['date_counts_scope']=='unknown'
    assert row['date_counts']['missing_invalid_dates']==0  # no clamping/rewriting
