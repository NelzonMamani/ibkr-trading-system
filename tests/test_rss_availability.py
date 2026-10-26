"""Synthetic bytes only: no acquisition, redirects, broker or operational writes."""
from datetime import datetime, timezone
from email.utils import format_datetime
from types import SimpleNamespace as NS
import socket
import time

import pytest
import requests

from src.news import news_fetcher as f
from src.news.feed_pool import SharedFeedPool
from src.news.news_intelligence_contract import NewsRequest
from src.news.rss_batch_runtime import news_provider_status
from src.news.rss_lifecycle import RssFetchLifecycle, capture_source_timing
from src.strategies.ross_momentum.policy.catalyst_policy import select_qualification_evidence

URL='https://fixture.invalid/rss'
RSS_EMPTY=b'<rss version="2.0"><channel><title>Empty feed</title></channel></rss>'
ATOM_EMPTY=b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty feed</title></feed>'
MALFORMED=RSS_EMPTY[:-6]


def populated(kind='rss'):
    if kind=='atom':
        return ('<feed xmlns="http://www.w3.org/2005/Atom"><title>Fixture</title><entry>'
                '<title>Azitra Inc reports earnings beat</title><id>urn:fixture</id>'
                '<link href="https://fixture.invalid/article"/><published>'+
                datetime.now(timezone.utc).isoformat()+'</published></entry></feed>').encode()
    return ('<rss version="2.0"><channel><title>Fixture</title><item><title>Azitra Inc reports earnings beat</title>'
            '<link>https://fixture.invalid/article</link><pubDate>'+format_datetime(datetime.now(timezone.utc))+
            '</pubDate></item></channel></rss>').encode()


class Response:
    def __init__(self, body, status=200):
        self.body,self.status_code,self.closes,self.reads=body,status,0,0
        self.headers={'Location':'https://forbidden.invalid/redirect-target'}
    @property
    def text(self):
        self.reads+=1
        return self.body.decode()
    def iter_content(self,chunk_size):
        self.reads+=1
        yield self.body
    def close(self):self.closes+=1
    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError(response=self)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('External socket attempted')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket.socket,'connect_ex',forbidden)


def fetch(life=None,pool=None,tier='fast'):
    return f.fetch_headlines_for_symbols(['AZTR'],[URL],lookback_hours=6,request_timeout_s=5,
        total_news_budget_seconds=8,source_tier=tier,lifecycle=life,feed_pool=pool,
        symbol_metadata={'AZTR':{'company_name':'AZITRA INC'}},source_groups_by_url={URL:'FAST_TRADING'},
        retention_selector=select_qualification_evidence,
        retention_request=NewsRequest(max_evidence_per_symbol=6,metadata={'presentation_limit':5}))


@pytest.mark.parametrize('tier',['fast','operational_query','research'])
@pytest.mark.parametrize('body,status,code',[
    (b'',301,'HTTP_301'),(b'<html>redirect</html>',301,'HTTP_301'),
    (b'<html>not RSS</html>',200,'RSSFEEDFORMATERROR'),(b'',200,'RSSFEEDFORMATERROR'),
    (b'not a feed',200,'RSSFEEDFORMATERROR'),(MALFORMED,200,'RSSFEEDPARSEERROR'),
    (b'access denied',401,'HTTP_401'),(b'access denied',403,'HTTP_403'),
])
def test_unavailable_source_is_never_available_empty(monkeypatch,tier,body,status,code):
    calls=[];response=Response(body,status)
    def get(url,**kw):
        calls.append((url,kw));return response
    monkeypatch.setattr(f.requests,'get',get)
    life=RssFetchLifecycle()
    try:
        rows,summary=fetch(life=life,tier=tier)
        assert rows['AZTR']==[] and news_provider_status(summary)=='provider_request_failure'
        route=summary.source_diagnostics[0]
        assert route['retrieval_status']=='provider_error' and route['failure_reason']==code
        assert len(calls)==1 and calls[0][0]==URL and calls[0][1]['allow_redirects'] is False
        assert 0<calls[0][1]['timeout']<=5
        if status==301:assert response.reads==0
    finally:
        assert life.wait_for_cleanup(2)['cleanup_complete']
        assert response.closes==1


@pytest.mark.parametrize('tier',['fast','operational_query','research'])
@pytest.mark.parametrize('body',[RSS_EMPTY,ATOM_EMPTY])
def test_legitimate_empty_rss_or_atom_is_available(monkeypatch,tier,body):
    response=Response(body);monkeypatch.setattr(f.requests,'get',lambda *a,**kw:response)
    life=RssFetchLifecycle()
    try:
        rows,summary=fetch(life=life,tier=tier)
        assert not rows['AZTR'] and news_provider_status(summary)=='available'
        assert summary.source_diagnostics[0]['retrieval_status']=='available'
    finally:
        assert life.wait_for_cleanup(2)['cleanup_complete'] and response.closes==1


@pytest.mark.parametrize('owned',[False,True])
@pytest.mark.parametrize('body',[RSS_EMPTY,ATOM_EMPTY,MALFORMED,b'',b'<html/>'])
def test_direct_transport_validation_and_closure(monkeypatch,owned,body):
    response=Response(body);calls=[]
    def get(url,**kw):calls.append(kw);return response
    monkeypatch.setattr(f.requests,'get',get)
    if owned:
        with capture_source_timing(True) as timing:
            timing['_bounded_operational']=True
            try:
                if body in (RSS_EMPTY,ATOM_EMPTY):assert f._fetch_feed(URL,5).version
                else:
                    with pytest.raises(f.RssFeedFormatError):f._fetch_feed(URL,5)
            finally:
                # Owned response must remain open for the lifecycle's callback.
                assert response.closes==0 and timing['_response'] is response
                response.close()
    else:
        if body in (RSS_EMPTY,ATOM_EMPTY):assert f._fetch_feed(URL,5).version
        else:
            with pytest.raises(f.RssFeedFormatError):f._fetch_feed(URL,5)
        assert response.closes==1
    assert len(calls)==1 and calls[0]['allow_redirects'] is False


@pytest.mark.parametrize('tier',['fast','operational_query'])
def test_missing_parser_version_cannot_bypass_validation(monkeypatch,tier):
    monkeypatch.setattr(f,'_fetch_feed',lambda *a:NS(entries=[],feed={}))
    life=RssFetchLifecycle()
    try:
        rows,summary=fetch(life=life,tier=tier)
        assert not rows['AZTR'] and summary.failure_count==1
        assert summary.source_diagnostics[0]['failure_reason']=='RSSFEEDFORMATERROR'
    finally:assert life.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('status,body,available',[(301,b'',False),(200,b'<html/>',False),(200,MALFORMED,False),(200,RSS_EMPTY,True)])
def test_shared_pool_reuses_honest_failure_or_valid_empty(monkeypatch,status,body,available):
    responses=[]
    def get(url,**kw):
        r=Response(body,status);responses.append(r);return r
    monkeypatch.setattr(f.requests,'get',get)
    pool=SharedFeedPool(ttl=60,failure_backoff=60)
    for index in range(2):
        life=RssFetchLifecycle()
        try:
            rows,summary=fetch(life=life,pool=pool,tier='operational_query')
            assert not rows['AZTR']
            assert news_provider_status(summary)==('available' if available else 'provider_request_failure')
            assert summary.source_diagnostics[0]['entry_diagnostics']['transport_cache_hit']==bool(index)
        finally:assert life.wait_for_cleanup(2)['cleanup_complete']
    assert pool.requests==1 and len(responses)==1 and responses[0].closes==1
    assert (pool.cache[URL][1]['error'] is None)==available


@pytest.mark.parametrize('tier',['fast','operational_query'])
@pytest.mark.parametrize('kind',['rss','atom'])
def test_valid_populated_feed_still_delivers_original_fresh_article(monkeypatch,tier,kind):
    response=Response(populated(kind));monkeypatch.setattr(f.requests,'get',lambda *a,**kw:response)
    life=RssFetchLifecycle()
    try:
        rows,summary=fetch(life=life,tier=tier)
        assert news_provider_status(summary)=='available'
        assert len(rows['AZTR'])==1 and rows['AZTR'][0].title=='Azitra Inc reports earnings beat'
        assert 0<=time.time()-rows['AZTR'][0].published_ts<=21600
        import calendar
        assert rows['AZTR'][0].published_ts==calendar.timegm(f.feedparser.parse(response.body).entries[0].published_parsed)
    finally:assert life.wait_for_cleanup(2)['cleanup_complete'] and response.closes==1


def test_missing_requests_never_delegates_network_to_parser(monkeypatch):
    calls=[]
    monkeypatch.setattr(f,'requests',None)
    monkeypatch.setattr(f,'feedparser',NS(parse=lambda *a:calls.append(a)))
    with pytest.raises(RuntimeError):f._fetch_feed(URL,5)
    assert calls==[]


@pytest.mark.parametrize('compatible',[False,True])
def test_old_cached_availability_cannot_certify_new_validation_contract(monkeypatch,tmp_path,compatible):
    from dataclasses import replace
    import hashlib,json
    from src.news import batch_rss_adapter as adapter, news_intelligence_service as service
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_contract import NewsCandidate,RetrievalPolicy
    monkeypatch.setattr(adapter,'get_source_group_urls',lambda group:(URL,) if group=='FAST_TRADING' else ())
    monkeypatch.setattr(service,'get_source_group_urls',lambda group:(URL,) if group=='FAST_TRADING' else ())
    calls=[]
    def get(*a,**kw):calls.append(1);return Response(RSS_EMPTY)
    monkeypatch.setattr(f.requests,'get',get)
    life=RssFetchLifecycle()
    store=CanonicalNewsEvidenceStore(tmp_path/'news.json',prep_artifact_loader=lambda:{})
    provider=adapter.BatchRssNewsIntelligenceProvider(lifecycle=life)
    canonical=service.CanonicalNewsIntelligenceService(evidence_store=store,retrieval_provider=provider)
    policy=RetrievalPolicy(source_groups=('FAST_TRADING',),fallback_mode='none',refresh_mode='bounded_refresh',
        network_allowed=True,refresh_interval_seconds=120,metadata={'require_compatible_acquisition':compatible})
    candidates=(NewsCandidate('AZTR',company_name='AZITRA INC'),)
    request=NewsRequest()
    try:
        fresh=canonical.get_news(candidates,request,policy)
        assert fresh.summary_for_symbol('AZTR').provider_available is True and len(calls)==1
        data=json.loads(store.cache_path.read_text())
        previous=data['news_intelligence']['symbols']['AZTR']['last_retrieval']
        previous.pop('rss_availability_contract',None)
        if compatible:
            profile=previous['acquisition_profile']
            profile['retrieval'].pop('rss_availability_contract',None)
            profile.pop('fingerprint',None)
            profile['fingerprint']=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        store.cache_path.write_text(json.dumps(data))
        before=store.cache_path.read_bytes()
        cached=canonical.get_news(candidates,request,replace(policy,network_allowed=False,
            refresh_mode='cache_only',allow_cache_write=False))
        summary=cached.summary_for_symbol('AZTR')
        assert summary.provider_status=='coverage_unknown' and summary.provider_available is None
        assert cached.diagnostics.provider_available is None
        assert len(calls)==1 and store.cache_path.read_bytes()==before
    finally:assert life.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('compatible',[False,True])
def test_unavailable_adapter_result_and_canonical_cache_reuse_stay_unavailable(monkeypatch,tmp_path,compatible):
    from dataclasses import replace
    from src.news import batch_rss_adapter as adapter, news_intelligence_service as service
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_contract import NewsCandidate,RetrievalPolicy
    for module in (adapter,service):
        monkeypatch.setattr(module,'get_source_group_urls',lambda group:(URL,) if group=='FAST_TRADING' else ())
    calls=[];responses=[]
    def get(*a,**kw):
        calls.append(kw);r=Response(b'',301);responses.append(r);return r
    monkeypatch.setattr(f.requests,'get',get)
    life=RssFetchLifecycle();pool=SharedFeedPool()
    store=CanonicalNewsEvidenceStore(tmp_path/'news.json',prep_artifact_loader=lambda:{})
    provider=adapter.BatchRssNewsIntelligenceProvider(lifecycle=life,feed_pool=pool)
    canonical=service.CanonicalNewsIntelligenceService(evidence_store=store,retrieval_provider=provider)
    policy=RetrievalPolicy(source_groups=('FAST_TRADING',),fallback_mode='none',refresh_mode='bounded_refresh',
        network_allowed=True,refresh_interval_seconds=120,metadata={'require_compatible_acquisition':compatible})
    candidates=(NewsCandidate('AZTR',company_name='AZITRA INC'),)
    request=NewsRequest()
    try:
        for index in range(3):
            result=canonical.get_news(candidates,request,policy if index==0 else replace(
                policy,network_allowed=False,refresh_mode='cache_only',allow_cache_write=False))
            summary=result.summary_for_symbol('AZTR')
            assert not result.evidence_for_symbol('AZTR') and summary.provider_available is False
            assert result.diagnostics.provider_available is False
            assert summary.provider_status=='provider_request_failure'
        assert len(calls)==pool.requests==1
        # A second adapter consumer reuses the cached transport failure as failure.
        raw=provider.get_news(candidates,request,policy)
        assert raw.diagnostics.provider_available is False and not raw.evidence_for_symbol('AZTR')
        assert len(calls)==1
    finally:
        assert life.wait_for_cleanup(2)['cleanup_complete'] and responses[0].closes==1


def test_mixed_valid_and_redirect_sources_preserve_explicit_partial_reporting(monkeypatch):
    responses=[]
    def get(url,**kw):
        response=Response(RSS_EMPTY if url.endswith('valid') else b'',200 if url.endswith('valid') else 301)
        responses.append(response);return response
    monkeypatch.setattr(f.requests,'get',get)
    life=RssFetchLifecycle()
    try:
        rows,summary=f.fetch_headlines_for_symbols(['AZTR'],[URL+'/valid',URL+'/redirect'],
            lifecycle=life,source_tier='fast',total_news_budget_seconds=8)
        assert not rows['AZTR'] and summary.failure_count==1
        assert news_provider_status(summary)=='partial_request_failure'
        assert {r['retrieval_status'] for r in summary.source_diagnostics}=={'available','provider_error'}
    finally:assert life.wait_for_cleanup(2)['cleanup_complete'] and all(r.closes==1 for r in responses)


@pytest.mark.parametrize('status',[301,302,303,304,307,308,399])
def test_every_redirect_shape_is_rejected_before_parser_or_body(monkeypatch,status):
    response=Response(b'not evidence',status)
    def get(url,**kw):
        assert url==URL and kw['allow_redirects'] is False
        return response
    monkeypatch.setattr(f.requests,'get',get)
    monkeypatch.setattr(f.feedparser,'parse',lambda *a:pytest.fail('Redirect entered parser'))
    with pytest.raises(f.RssFeedRedirectError) as caught:f._fetch_feed(URL,5)
    assert f._failure_code(caught.value)=='HTTP_'+str(status)
    assert response.closes==1 and response.reads==0


def test_raw_capture_preserves_unfollowed_redirect_as_incomplete_without_body_leak(monkeypatch,tmp_path):
    import json
    from src.news.rss_raw_capture import RawFeedCapture
    response=Response(b'private DU1234567',301)
    monkeypatch.setattr(f.requests,'get',lambda *a,**kw:response)
    capture=RawFeedCapture(tmp_path/'raw')
    with capture_source_timing(True) as timing:
        timing['_raw_capture']=capture
        try:
            with pytest.raises(f.RssFeedRedirectError):f._fetch_feed(URL,5)
        finally:
            assert timing['_response'] is response
            response.close()
    manifest=json.loads(next((tmp_path/'raw').glob('*.json')).read_text())
    assert manifest['http_status']==301 and not manifest['body_complete'] and manifest['bytes_captured']==0
    assert manifest['error']=='RssFeedRedirectError' and response.reads==0
    assert all(b'DU1234567' not in p.read_bytes() for p in (tmp_path/'raw').iterdir())


@pytest.mark.parametrize('body,status,code',[(RSS_EMPTY,301,'HTTP_301'),(b'',200,'RSSFEEDFORMATERROR'),(MALFORMED,200,'RSSFEEDPARSEERROR')])
def test_preexisting_unvalidated_pool_payload_cannot_become_available(monkeypatch,body,status,code):
    pool=SharedFeedPool()
    pool.cache[URL]=(time.monotonic()+60,{'feed':f.feedparser.parse(body),'error':None,
        'http_status':status,'completed_at_s':time.monotonic(),'_response':None})
    monkeypatch.setattr(f.requests,'get',lambda *a,**kw:pytest.fail('Cached invalid result triggered request'))
    life=RssFetchLifecycle()
    try:
        rows,summary=fetch(life=life,pool=pool,tier='fast')
        assert not rows['AZTR'] and news_provider_status(summary)=='provider_request_failure'
        assert summary.source_diagnostics[0]['failure_reason']==code and pool.requests==0
    finally:assert life.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('compatible',[False,True])
def test_legacy_negative_facts_survive_separately_from_current_coverage(monkeypatch,tmp_path,compatible):
    from dataclasses import replace
    import hashlib,json
    from src.news import batch_rss_adapter as adapter, news_intelligence_service as service
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_contract import NewsCandidate,RetrievalPolicy
    for module in (adapter,service):
        monkeypatch.setattr(module,'get_source_group_urls',lambda group:(URL,) if group=='FAST_TRADING' else ())
    calls=[]
    def get(*a,**kw):calls.append(1);return Response(b'',301)
    monkeypatch.setattr(f.requests,'get',get)
    life=RssFetchLifecycle()
    store=CanonicalNewsEvidenceStore(tmp_path/'news.json',prep_artifact_loader=lambda:{})
    canonical=service.CanonicalNewsIntelligenceService(evidence_store=store,
        retrieval_provider=adapter.BatchRssNewsIntelligenceProvider(lifecycle=life))
    candidates=(NewsCandidate('AZTR',company_name='AZITRA INC'),)
    policy=RetrievalPolicy(source_groups=('FAST_TRADING',),fallback_mode='none',refresh_mode='bounded_refresh',
        network_allowed=True,refresh_interval_seconds=120,metadata={'require_compatible_acquisition':compatible})
    try:
        fresh=canonical.get_news(candidates,NewsRequest(),policy)
        assert fresh.summary_for_symbol('AZTR').provider_available is False
        data=json.loads(store.cache_path.read_text())
        previous=data['news_intelligence']['symbols']['AZTR']['last_retrieval']
        previous.pop('rss_availability_contract')
        if compatible:
            profile=previous['acquisition_profile']
            profile['retrieval'].pop('rss_availability_contract')
            profile.pop('fingerprint')
            profile['fingerprint']=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        store.cache_path.write_text(json.dumps(data));before=store.cache_path.read_bytes()
        result=canonical.get_news(candidates,NewsRequest(),replace(policy,network_allowed=False,
            refresh_mode='cache_only',allow_cache_write=False))
        summary=result.summary_for_symbol('AZTR')
        assert summary.provider_available is (None if compatible else False)
        assert summary.provider_status==('coverage_unknown' if compatible else 'provider_request_failure')
        assert summary.diagnostics['last_retrieval']['provider_available'] is False
        assert summary.diagnostics['last_retrieval']['provider_status']=='provider_request_failure'
        if compatible:
            source=summary.diagnostics['last_retrieval']['coverage']['source_diagnostics'][0]
            assert source['failure_reason']=='HTTP_301'
        assert len(calls)==1 and store.cache_path.read_bytes()==before
    finally:assert life.wait_for_cleanup(2)['cleanup_complete']
