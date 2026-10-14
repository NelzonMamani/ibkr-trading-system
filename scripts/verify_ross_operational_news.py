"""Supervised broker-free invocation of the existing Ross news consumer.

Only RSS acquisition and catalyst policy run. This never starts a scanner cycle,
market-data provider, broker, selection or trading runtime. Default is cache-only;
live acquisition requires --enable-issuer-query. Outputs are isolated and new.
"""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_consumer(candidates, directory: Path, *, enabled: bool):
    from scripts.verify_news_discovery import _source_identity
    from src.config.config_resolver import set_config_overrides
    from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
    from src.news.rss_lifecycle import RssFetchLifecycle
    from src.news.standalone_lookup import jsonable
    from src.scanner import scanner_runner as ross
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst

    identity = _source_identity()
    extra_paths = [ROOT/'src/scanner/scanner_runner.py', *sorted((ROOT/'src/strategies/ross_momentum/policy').glob('*.py')),
                   ROOT/'src/config/config_registry.py', Path(__file__).resolve()]
    import hashlib
    before = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in extra_paths}
    identity['source_hashes'].update(before)
    lifecycle = RssFetchLifecycle()
    service = CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(directory/'canonical-cache.json', prep_artifact_loader=lambda:{}),
        retrieval_provider=BatchRssNewsIntelligenceProvider(lifecycle=lifecycle,raw_feed_directory=directory/'raw-feeds'))
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':enabled, 'NEWS_ENABLED':True,
        'NEWS_CACHE_FILE':str(directory/'canonical-cache.json'), 'NEWS_TOTAL_BUDGET_S':8.0,
        'NEWS_LOOKBACK_HOURS':6.0, 'NEWS_MAX_AGE_HOURS':6.0, 'NEWS_REQUEST_TIMEOUT_S':5,
        'NEWS_MAX_ENTRIES_PER_SYMBOL':5, 'ROSS_VALIDATION_OVERRIDE_ENABLED':False})
    captured_results=[]
    get_news=service.get_news
    def observe(*args, **kwargs):
        result=get_news(*args, **kwargs)
        captured_results.append(result)
        return result
    service.get_news=observe
    started=time.monotonic()
    try:
        metadata={c.normalized_symbol:{**c.metadata, 'company_name':c.company_name,'aliases':c.aliases,'exchange':c.exchange} for c in candidates}
        # Dependency substitution supplies an isolated instance of the SAME service,
        # not a second consumer, engine, prep store or qualification authority.
        with patch.object(ross,'_news_intelligence_service_for_scanner',lambda:service), patch.object(ross,'_NEWS_CACHE',{}):
            contexts,diagnostics=ross._enrich_news_context([c.normalized_symbol for c in candidates], 'RSS' if enabled else 'MOCK', metadata)
        cleanup=lifecycle.snapshot()
        report={'schema':'ross.operational_news_verification.v1', 'runtime':identity,
            'setting_enabled':enabled,'consumer':'src.scanner.scanner_runner._enrich_news_context',
            'contexts':contexts, 'diagnostics':asdict(diagnostics),
            'canonical_results':[jsonable(result) for result in captured_results],
            'mandatory_catalyst_decisions':{s:asdict(assess_catalyst(mode='READ_ONLY',news_enabled=True,
                news_available=ctx['news_available'],confirmed=ctx['ross_catalyst_valid'],validation_bypass_requested=False)) for s,ctx in contexts.items()},
            'cleanup':cleanup,'consumer_elapsed_seconds':time.monotonic()-started,
            'limits':'Eight-second acquisition, existing six-hour Ross freshness, five display slots plus one policy witness. Raw responses are separate evidence. Google URLs remain intermediary URLs. No trading-readiness upgrade.'}
        # Keep acquisition evidence before the separate diagnostic cleanup wait.
        report['worker_stage']='acquisition_complete_cleanup_pending'
        (directory/'operational-evidence.json').write_text(json.dumps(jsonable(report),indent=2)+'\n',encoding='utf-8')
        report['cleanup']=lifecycle.wait_for_cleanup(10.0)
        report['worker_stage']='cleanup_wait_complete'
        after=_source_identity()['source_hashes']
        after.update({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in extra_paths})
        report['runtime']['source_hashes_unchanged']=identity['source_hashes']==after
        return jsonable(report)
    finally:
        set_config_overrides({})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates-file',type=Path)
    parser.add_argument('--output-directory',type=Path)
    parser.add_argument('--enable-issuer-query',action='store_true')
    parser.add_argument('--_worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not args.candidates_file or not args.output_directory:
        parser.error('--candidates-file and --output-directory are required')
    directory=args.output_directory.resolve()
    if not args._worker:
        directory.mkdir(parents=True,exist_ok=False)
        command=[sys.executable,str(Path(__file__).resolve()),'--_worker','--candidates-file',str(args.candidates_file.resolve()),'--output-directory',str(directory)]
        if args.enable_issuer_query:
            command.append('--enable-issuer-query')
        # 10s import/startup + 8s acquisition + 10s owned cleanup + 5s exit.
        started=time.monotonic()
        with (directory/'human.txt').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            try:
                code=process.wait(timeout=33)
                terminated=False
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5);code=124;terminated=True
        outcome={'exit_code':code,'wall_seconds':time.monotonic()-started,'wall_limit_seconds':33,
                 'terminated':terminated,'cleanup_proven':False if terminated else None}
        (directory/'process.json').write_text(json.dumps(outcome,indent=2)+'\n',encoding='utf-8')
        print((directory/'human.txt').read_text(encoding='utf-8'))
        print('Evidence directory: '+str(directory))
        return code
    from scripts.verify_news_discovery import _candidate_from_mapping
    data=json.loads(args.candidates_file.read_text(encoding='utf-8-sig'))
    candidates=[_candidate_from_mapping(x) for x in (data.get('candidates') if isinstance(data,dict) else data)]
    if not 1 <= len(candidates) <= 50 or any(not c.company_name for c in candidates):
        raise ValueError('Supply 1–50 full issuer identities; at most four distinct queries are scheduled')
    try:
        result=run_consumer(candidates,directory,enabled=args.enable_issuer_query)
        (directory/'operational-evidence.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        for symbol,context in result['contexts'].items():
            print(symbol,json.dumps({'valid':context.get('ross_catalyst_valid'),'status':context.get('news_diagnostic_status'),
                'decisions':context.get('qualification_decisions',[])}))
        print('Cleanup: '+json.dumps(result['cleanup']))
        return 0 if result['cleanup'].get('cleanup_complete') is True else 2
    except Exception as exc:
        (directory/'failure.json').write_text(json.dumps({'error':type(exc).__name__,'message':str(exc)},indent=2)+'\n',encoding='utf-8')
        raise


if __name__=='__main__':
    raise SystemExit(main())
