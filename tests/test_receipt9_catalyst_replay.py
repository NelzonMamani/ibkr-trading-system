"""Receipt9 facts only: no acquisition, runtime, writes to receipt, or forced Focus."""
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from src.news.evidence_store import evidence_from_mapping, summarize_news_evidence
from src.news.news_intelligence_contract import NewsBatchResult, NewsCandidate, RetrievalDiagnostics
from src.scanner import scanner_runner as ross
from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst
from test_news_catalyst_lifecycle_audit import lifecycle
from test_watchlist_between_scan_reassessment import reassessment
from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _row, _payload, _cadence, _age_cache

FACTS = json.loads((Path(__file__).parent/'fixtures/ross_receipt9_catalyst.json').read_text())


def batch(symbol, now):
    row = FACTS['symbols'][symbol]
    candidate = NewsCandidate(symbol, company_name=row['issuer']['company_name'])
    request = ross._ross_news_request()
    evidence = tuple(evidence_from_mapping(a, request=request, now=now) for a in row['evidence'])
    assert all(evidence)
    summary = summarize_news_evidence(symbol, evidence, request=request,
        retrieval_status=row['retrieval_status'], provider_status=row['provider_status'],
        provider_available=row['provider_available'], budget_exhausted=row['budget_exhausted'])
    result = NewsBatchResult(candidates=(candidate,), request=request,
        evidence_by_symbol={symbol:evidence}, summaries_by_symbol={symbol:summary},
        diagnostics=RetrievalDiagnostics(provider_available=row['provider_available'],
            provider_status=row['provider_status'], retrieval_status=row['retrieval_status'],
            diagnostics={'operational_acquisition_by_symbol':{symbol:row['acquisition_scope']}}))
    return result


@pytest.mark.parametrize('symbol',FACTS['symbols'])
def test_final_retained_facts_replay_strict_negative(lifecycle, symbol):
    # Frozen final-snapshot clock: never retroject final cache into earlier scans.
    now = datetime.fromisoformat(FACTS['replay_at'])
    lifecycle.clock.current = now
    result = batch(symbol, now)
    context = ross._ross_news_contexts_from_news_intelligence_result(result)[symbol]
    assert context['ross_catalyst_valid'] is False
    assert context['qualification_reason'] == 'no_valid_canonical_event'
    assert context['news_available'] is False
    assert context['acquisition_health'] == 'degraded'
    decision = assess_catalyst(mode='READ_ONLY',news_enabled=True,
        news_available=context['news_available'],confirmed=None)
    assert decision.status.value == 'DATA_UNAVAILABLE' and not decision.satisfied
    for article in context.get('qualification_decisions', ()):
        assert article['reason'] == 'no_catalyst_classification'
    assert len(context.get('qualification_decisions',())) == len(FACTS['symbols'][symbol]['evidence'])
    assert lifecycle.provider.calls == 0


@pytest.mark.parametrize('symbol',('PFSA','NCPL'))
def test_core_reconsiders_receipt_commentary_without_rescan_or_http(reassessment, monkeypatch, symbol):
    from src.config import config_resolver
    from src.core import orchestrator as core_module
    c = reassessment
    now = datetime.fromisoformat(FACTS['replay_at'])
    c.life.clock.current = now
    c.row.update(symbol=symbol,company_name=FACTS['symbols'][symbol]['issuer']['company_name'])
    bundle = c.payload['ross_watchlist_reassessment']
    bundle['date'] = now.date().isoformat()
    payload = _payload([_row(symbol)],focus=[])
    payload.update(c.payload)
    core, scans, processed = _install_runtime_harness(monkeypatch,[payload])
    overrides = dict(config_resolver._CONFIG_OVERRIDES)
    overrides.update(NEWS_ENABLED=True,ROSS_ISSUER_QUERY_ENABLED=True,
                     NEWS_CACHE_FILE=str(c.life.store.cache_path))
    config_resolver.set_config_overrides(overrides)
    _, policy = core._build_scanner_policy_for_strategy('ross_momentum','RTH_OPEN')
    bundle['policy'] = policy
    bundle['thresholds'] = ross._gate_thresholds(policy,ross._resolve_runtime_thresholds(policy,'RTH_OPEN'))
    core.connection_manager._client = object()  # Controlled identity; never connected.
    c.provider.market_data_client = core.connection_manager.optional_client
    scanner_stub = core_module.run_scanner_cycle
    def scan(**kwargs):
        ross._PERSISTENT_PROVIDER = c.provider
        return scanner_stub(**kwargs)
    monkeypatch.setattr(core_module,'run_scanner_cycle',scan)
    reads=[]
    published=[False]
    def read(candidates,request,policy):
        reads.append(tuple(candidate.symbol for candidate in candidates))
        if published[0]:return batch(symbol,now)
        return NewsBatchResult(candidates=tuple(candidates),request=request)
    core._news_maintenance = NS(read=read,set_active=lambda *args:None)
    assert core.run_once() and not _cadence(core).focus.symbols
    published[0]=True  # A recorded snapshot becomes visible; no acquisition/write.
    _age_cache(_cadence(core).focus,11)
    assert core.run_once()
    assert reads == [(symbol,)]
    assert len(scans)==1 and not _cadence(core).focus.symbols and processed==[]
    assert c.calls==[] and c.life.provider.calls==0


@pytest.mark.parametrize('symbol',('PFSA','NCPL'))
def test_real_canonical_reader_keeps_receipt_facts_without_network_or_rewrite(lifecycle, symbol):
    from dataclasses import replace
    import hashlib
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
    row=FACTS['symbols'][symbol]
    lifecycle.clock.current=datetime.fromisoformat(FACTS['replay_at'])
    path=lifecycle.store.cache_path
    path.write_text(json.dumps({'news_intelligence':{'schema_version':'PR1069.news_intelligence_evidence_store.v1',
        'symbols':{symbol:{'evidence':row['evidence'],'ross_qualification_evidence':row['evidence'],
                          'updated_at':row['updated_at']}}}}))
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    class ForbiddenProvider:
        provider_id='rss_batch'
        def get_news(self,*args,**kwargs):pytest.fail('Acquisition forbidden in receipt replay')
    service=CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(path,prep_artifact_loader=lambda:{}),
        retrieval_provider=ForbiddenProvider())
    candidate=NewsCandidate(symbol,company_name=row['issuer']['company_name'])
    result=service.get_news((candidate,),ross._ross_news_request(),replace(lifecycle.policy,
        network_allowed=False,refresh_mode='cache_only',allow_cache_write=False))
    actual=ross._ross_news_contexts_from_news_intelligence_result(result)[symbol]
    assert len(result.evidence_for_symbol(symbol))==len(row['evidence'])
    assert [a.published_at.isoformat() for a in result.evidence_for_symbol(symbol)]==[a['published_at'] for a in row['evidence']]
    assert not actual['ross_catalyst_valid']
    assert {d['reason'] for d in actual['qualification_decisions']}=={'no_catalyst_classification'}
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
