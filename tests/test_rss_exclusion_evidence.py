"""Controlled response replay: unchanged freshness/matching and bounded diagnostics."""
from datetime import datetime, timezone
from email.utils import formatdate
import json
import time
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
    monkeypatch.setattr(fetcher,'_fetch_feed',lambda *args:NS(entries=entries,feed={'title':'Fixture'}))
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
        monkeypatch.setattr(fetcher,'_fetch_feed',lambda url,*args:NS(
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
        assert 'Unrelated fresh article' not in capsys.readouterr().out  # stdout stays content-free
    finally:
        assert lifecycle.wait_for_cleanup(2)['cleanup_complete']
        set_config_overrides({})
