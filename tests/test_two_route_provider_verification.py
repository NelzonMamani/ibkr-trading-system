"""Offline-only synthetic responses: no provider/broker request is permitted."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import hashlib
import json
from pathlib import Path
import subprocess
import socket
import sys
import threading
import time
from types import SimpleNamespace as NS
import zipfile

import pytest
import requests

from scripts.diagnostics import rss_feed_diagnostic as d
from scripts.diagnostics.verify_two_route_provider import PROFILE, DIAGNOSTIC
from scripts.diagnostics import verify_two_route_provider as entry

NOW = datetime(2026, 10, 26, 19, 0, tzinfo=timezone.utc)
SOURCE = {'head': 'a'*40, 'tree': 'b'*40, 'production_base': PROFILE.production}
EXPECTED = ('https://www.investing.com/rss/news.rss', 'https://www.forbes.com/business/feed2')


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('External network is forbidden during preparation')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)


def item(title='Azitra Inc reports earnings beat', summary='Synthetic assertion', age=60):
    from xml.sax.saxutils import escape
    date = '' if age is None else '<pubDate>'+format_datetime(NOW-timedelta(seconds=age))+'</pubDate>'
    return '<item><title>'+escape(title)+'</title><description>'+escape(summary)+'</description>'+date+'<link>https://synthetic.invalid/article</link></item>'


def xml(*entries):
    return ('<rss version="2.0"><channel><title>Synthetic offline two-route verification</title>'+''.join(entries)+'</channel></rss>').encode()


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.closed = data, status, False
    def iter_content(self, chunk_size):
        for i in range(0,len(self.data),chunk_size):
            yield self.data[i:i+chunk_size]
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)
    def close(self): self.closed=True


@pytest.fixture
def capture(monkeypatch, tmp_path):
    private=tmp_path/'private'; private.mkdir()
    calls=[]; responses=[]
    payload=xml(item())
    def get(url,**kwargs):
        assert url in EXPECTED and kwargs['allow_redirects'] is False and kwargs['stream'] is True
        assert 0 < kwargs['timeout'] <= 5
        calls.append((url,kwargs['timeout']))
        response=Response(payload)
        responses.append(response)
        return response
    monkeypatch.setattr(d.fetcher.requests,'get',get)
    def run():
        with DIAGNOSTIC.recorded_clock(NOW.isoformat()):
            session=DIAGNOSTIC.acquire(private,SOURCE)
        return session
    return NS(private=private, calls=calls,responses=responses,run=run)


def test_exact_shared_batch_cleanup_and_no_operational_writes(capture, tmp_path, monkeypatch):
    writes=[]
    original=Path.open
    def observed(path,mode='r',*args,**kwargs):
        if any(c in mode for c in 'wax+'):
            writes.append(path.resolve())
        return original(path,mode,*args,**kwargs)
    monkeypatch.setattr(Path,'open',observed)
    session=capture.run()
    assert PROFILE.urls==EXPECTED and len(capture.calls)==2
    assert {u for u,_ in capture.calls}==set(EXPECTED)
    assert all(r.closed for r in capture.responses)
    assert session['cleanup']['cleanup_complete'] and session['cleanup']['alive_worker_count']==0
    assert session['summary']['total_news_budget_seconds']==8
    assert session['summary']['sources_attempted_count']==2
    assert all(capture.private in p.parents for p in writes)
    report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert report['coverage_complete']
    assert all(r['offline_analysis']['per_issuer_reason_counts']['AZTR']=={'issuer_subject_event_attributed':1} for r in report['routes'])


def test_replay_recorded_clock_not_present_day_and_no_transport(capture,monkeypatch,tmp_path):
    session=capture.run()
    original=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    def forbidden(*a,**kw): pytest.fail('Replay attempted acquisition')
    monkeypatch.setattr(d.fetcher.requests,'get',forbidden)
    monkeypatch.setattr(d.fetcher,'fetch_headlines_for_symbols',forbidden)
    replay=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert replay==original
    report=replay['routes'][0]['offline_analysis']
    assert report['samples']['matched'][0]['issuer_decisions']['AZTR']['age_seconds']==60
    assert len(capture.calls)==2


@pytest.mark.parametrize('kind',['length','hash','clock','url','oversize','inventory','symlink'])
def test_replay_rejects_untrusted_capture(capture,kind,monkeypatch):
    session=capture.run()
    manifest=next((capture.private/'raw').glob('*.json'))
    record=json.loads(manifest.read_text());body=manifest.with_suffix('.xml')
    if kind=='length': record['bytes_captured']+=1
    elif kind=='hash': record['sha256']='0'*64
    elif kind=='clock': record['evaluation_time_utc']=(NOW+timedelta(seconds=1)).isoformat()
    elif kind=='url': record['url']='https://evil.invalid'
    elif kind=='oversize': body.write_bytes(b'x'*(d.RAW_FEED_BYTES+1))
    elif kind=='inventory': (capture.private/'raw'/'extra.xml').write_bytes(b'x')
    else:
        original=Path.is_symlink
        monkeypatch.setattr(Path,'is_symlink',lambda p:p==body or original(p))
    manifest.write_text(json.dumps(record))
    with pytest.raises(ValueError):DIAGNOSTIC.build_report(capture.private,session,SOURCE)


def test_bounds_sanitization_reason_counts_and_zip_excludes_raw(tmp_path):
    data=xml(*[item('Unrelated issuer DU1234567 '+ 'x'*2000, 'summary DU1234567 '+'x'*3000) for _ in range(20)],
        item('Azitra Inc reports earnings beat'),item('Azitra Inc files Form 8-K','Azitra Inc reports earnings beat'),
        item(age=21601),item(age=-1),item(age=None))
    report=DIAGNOSTIC.adjudicate(data,NOW.isoformat())
    assert report['entries_examined']==25
    assert report['omitted_samples']['issuer_match_unverified']==18
    assert len(report['samples']['issuer_match_unverified'])==2
    sample=report['samples']['issuer_match_unverified'][0]
    assert sample['privacy_redacted'] and sample['title_truncated'] and sample['summary_truncated']
    assert len(sample['title'])<=512 and len(sample['summary'])<=1024
    assert 'DU1234567' not in json.dumps(report)
    assert report['per_issuer_reason_counts']['AZTR']=={
        'issuer_match_unverified':20,'issuer_subject_event_attributed':1,'no_catalyst_classification':1,
        'outside_lookback_window':1,'future_publication_time':1,'missing_publication_time':1}
    (tmp_path/'private').mkdir();(tmp_path/'private'/'raw.xml').write_bytes(data)
    digest=DIAGNOSTIC.package(tmp_path,report)
    archive=tmp_path/'ross-two-route-provider-shareable.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
    with zipfile.ZipFile(archive) as z:
        assert z.namelist()==['report.json','privacy.json']
        assert json.loads(z.read('privacy.json'))['passed']
        assert b'DU1234567' not in z.read('report.json')
    assert not (tmp_path/'shareable'/'raw.xml').exists()


@pytest.mark.parametrize('status',[200,401,403,302])
def test_http_failure_and_byte_truncation_are_not_valid_coverage(capture,monkeypatch,status):
    def get(url,**kwargs):
        assert kwargs['allow_redirects'] is False
        response=Response(b'x'*(d.RAW_FEED_BYTES+1) if status==200 else b'private DU1234567',status)
        capture.responses.append(response);return response
    monkeypatch.setattr(d.fetcher.requests,'get',get)
    session=capture.run(); report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert not report['coverage_complete'] and not any(r['adjudicable'] for r in report['routes'])
    assert all(r.closed for r in capture.responses)
    assert len(list((capture.private/'raw').glob('*.xml')))==2
    assert sum(p.stat().st_size for p in (capture.private/'raw').glob('*.xml'))<=1024*1024
    if status==200:
        assert all(r['capture']['bytes_captured']==d.RAW_FEED_BYTES and not r['capture']['body_complete'] for r in report['routes'])
    assert 'DU1234567' not in json.dumps(report)


def test_incomplete_cleanup_never_reads_or_packages_bodies(capture,monkeypatch):
    original=d.RssFetchLifecycle
    class Incomplete(original):
        def wait_for_cleanup(self,seconds):
            assert seconds==10
            snapshot=super().wait_for_cleanup(seconds)
            snapshot['cleanup_complete']=False
            return snapshot
    monkeypatch.setattr(d,'RssFetchLifecycle',Incomplete)
    with pytest.raises(RuntimeError,match='did not stop'):capture.run()
    assert not (capture.private.parent/'shareable').exists()


def test_budget_clipped_to_remaining_without_retries(capture,monkeypatch):
    # Advance the coordinator's monotonic clock at the first transport boundary.
    # The second request may already be scheduled; any unattempted tail must remain
    # unattempted, not receive a fresh 8-second allowance or retries.
    original=d.fetcher.time
    elapsed=[0.]
    proxy=NS(time=original.time,monotonic=lambda:original.monotonic()+elapsed[0])
    monkeypatch.setattr(d.fetcher,'time',proxy)
    def get(url,**kwargs):
        assert 0 < kwargs['timeout']<=5
        capture.calls.append((url,kwargs['timeout']))
        elapsed[0]=9.
        return Response(xml(item()))
    monkeypatch.setattr(d.fetcher.requests,'get',get)
    # No recorded_clock wrapper: retain the monotonic deadline control.
    session=DIAGNOSTIC.acquire(capture.private,SOURCE)
    report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert 1<=len(capture.calls)<=2 and len({u for u,_ in capture.calls})==len(capture.calls)
    assert any(not r['attempted'] for r in report['routes'])
    assert not report['coverage_complete']


def test_new_output_disjoint_and_no_live_default(tmp_path):
    with pytest.raises(ValueError):DIAGNOSTIC.new_output(d.ROOT/'output')
    with pytest.raises(ValueError):DIAGNOSTIC.new_output(tmp_path)
    with pytest.raises(ValueError):DIAGNOSTIC.new_output(tmp_path/'private'/'child',tmp_path/'private')
    with pytest.raises(SystemExit):DIAGNOSTIC.main(entry.__file__, ['--output',str(tmp_path/'new'),'--expected-commit','a'*40])


def test_supervisor_timeout_kills_child_and_returns_sanitized_failure(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(DIAGNOSTIC,'identity',lambda expected:SOURCE)
    def timeout(command,**kwargs):
        assert '--acquire' in command and '-I' in command and kwargs['timeout']==45
        raise subprocess.TimeoutExpired(command,45)
    monkeypatch.setattr(d.subprocess,'run',timeout)
    assert DIAGNOSTIC.main(entry.__file__, ['--acquire','--output',str(tmp_path/'new'),'--expected-commit','a'*40])==1
    printed=json.loads(capsys.readouterr().out)
    with zipfile.ZipFile(printed['shareable_zip']) as z:
        assert json.loads(z.read('report.json'))['coverage_complete'] is False


def test_failure_to_get_response_has_no_hidden_acquisition_retry(capture,monkeypatch):
    calls=[]
    def fail(url,**kwargs):
        calls.append(url)
        raise requests.ConnectionError('private DU1234567')
    monkeypatch.setattr(d.fetcher.requests,'get',fail)
    session=capture.run(); report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert calls and len(calls)==len(set(calls))==2
    assert not report['coverage_complete']
    assert all(not row['adjudicable'] for row in report['routes'])
    assert 'DU1234567' not in json.dumps(report)


def test_report_rejects_different_replay_source(capture):
    session=capture.run()
    with pytest.raises(ValueError,match='same exact source'):
        DIAGNOSTIC.build_report(capture.private,session,dict(SOURCE,head='c'*40))


def test_missing_body_and_late_capture_do_not_become_complete_coverage(capture):
    session=capture.run()
    row=session['summary']['source_diagnostics'][0]
    row['retrieval_status']='budget_exhausted'
    row['processing_truncated']=True
    report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    route=next(r for r in report['routes'] if r['url']==row['source_id'])
    assert route['adjudicable'] and route['processing_truncated']
    assert not report['coverage_complete']
    assert route['analysis_scope']=='captured_body_replay_not_admission_or_in_budget_completion'
    manifest=next((capture.private/'raw').glob('*.json'))
    body=manifest.with_suffix('.xml');manifest.unlink();body.unlink()
    report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert not report['coverage_complete'] and any(not r['raw_capture_present'] for r in report['routes'])


def test_source_identity_is_fail_closed(monkeypatch):
    def git(command,**kwargs):
        if 'rev-parse' in command:return 'a'*40
        return ' M src/news/news_fetcher.py'
    monkeypatch.setattr(d.subprocess,'check_output',git)
    with pytest.raises(ValueError,match='mismatch'):DIAGNOSTIC.identity('b'*40)
    with pytest.raises(ValueError,match='clean'):DIAGNOSTIC.identity('a'*40)


def test_cli_help_imports_cannot_connect_or_publish(tmp_path):
    # Fresh process, outside pytest's existing module cache. Existing policy
    # facade may load SDK/type modules; no broker object/connection is started.
    code='''import socket, sys, runpy
socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('connection attempted'))
sys.argv = [sys.argv[1], '--help']
runpy.run_path(sys.argv[0], run_name='__main__')
'''
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(entry.__file__))],
                          capture_output=True,text=True,timeout=10,cwd=tmp_path)
    assert result.returncode==0 and 'usage:' in result.stdout and not result.stderr
    assert '[CONFIG]' not in result.stdout
    assert list(tmp_path.iterdir())==[]


if sys.platform=='win32':
    def test_windows_powershell51_operator_block_parses_without_execution(tmp_path):
        verifier=tmp_path/'parse-only.ps1'
        verifier.write_text('''param([string]$Target)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($Target,[ref]$tokens,[ref]$errors) | Out-Null
if ($errors.Count -gt 0) { throw ($errors | Out-String) }
Write-Output 'PARSER_ONLY_PASS'
''')
        target=d.ROOT/'scripts/diagnostics/Invoke-TwoRouteProviderVerification.ps1'
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(verifier),'-Target',str(target)],capture_output=True,text=True,timeout=20)
        assert result.returncode==0 and 'PARSER_ONLY_PASS' in result.stdout


def test_current_exact_boundary_updated_only_and_invalid_feed():
    data=xml(item(age=0),item(age=21600),item(age=21600.000001))
    # RSS seconds resolution means this fixture's subsecond value rounds to a
    # prior whole second. Publication timestamps are not clamped or substituted.
    analysis=DIAGNOSTIC.adjudicate(data,NOW.isoformat())
    assert analysis['per_issuer_reason_counts']['AZTR']['issuer_subject_event_attributed']==2
    assert analysis['per_issuer_reason_counts']['AZTR']['outside_lookback_window']==1
    entry=NS(title='Azitra Inc reports earnings beat',summary='',link='',
             updated_parsed=time.gmtime(NOW.timestamp()-60),updated='Mon, 26 Oct 2026 18:59:00 GMT')
    with DIAGNOSTIC.recorded_clock(NOW.isoformat()):
        *_,decisions=DIAGNOSTIC.entry_decisions(entry,NOW.timestamp())
    assert decisions['AZTR']['reason']=='publication_time_unverified_update_only'
    assert not DIAGNOSTIC.adjudicate(b'Not an RSS document',NOW.isoformat())['recognized_feed']


def test_transport_timeouts_never_exceed_remaining_shared_budget(capture):
    session=capture.run()
    assert len(session['transport_attempts'])==2
    for timing in session['transport_attempts'].values():
        assert 0 < timing['timeout_seconds'] <= min(5,timing['remaining_budget_seconds'])


if sys.platform=='win32':
    def test_windows_operator_rejects_nested_evidence_before_creation(tmp_path):
        verifier=tmp_path/'reject-nested.ps1'
        verifier.write_text('''param([string]$Target, [string]$Python, [string]$Source)
$ErrorActionPreference = 'Stop'
function git {
    $global:LASTEXITCODE = 0
    if ($args -contains 'HEAD^{tree}') { return ('b' * 40) }
    if ($args -contains 'rev-parse') { return ('a' * 40) }
}
$nested = Join-Path $Source 'evidence'
try {
    & $Target -ExpectedCommit ('a' * 40) -ExpectedTree ('b' * 40) -Python $Python -SourceCheckout $Source -EvidenceRoot $nested
    throw 'Nested output was unexpectedly allowed'
} catch {
    if ($_.Exception.Message -ne 'EvidenceRoot must be new and outside source.') { throw }
}
if (Test-Path -LiteralPath $nested) { throw 'Rejected output was created or ACL modified' }
Write-Output 'NESTED_REJECTION_BEFORE_CREATION_PASS'
''')
        source=tmp_path/'source';source.mkdir()
        target=d.ROOT/'scripts/diagnostics/Invoke-TwoRouteProviderVerification.ps1'
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(verifier),'-Target',str(target),'-Python',sys.executable,'-Source',str(source)],
            capture_output=True,text=True,timeout=20)
        assert result.returncode==0 and 'NESTED_REJECTION_BEFORE_CREATION_PASS' in result.stdout
        assert not (source/'evidence').exists()


def test_malformed_recognized_rss_cannot_claim_complete_coverage(capture,monkeypatch):
    malformed=xml(item())[:-6]  # Complete HTTP bytes, incomplete XML document.
    monkeypatch.setattr(d.fetcher.requests,'get',lambda *a,**kw:Response(malformed))
    session=capture.run()
    report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert all(r['offline_analysis']['recognized_feed'] for r in report['routes'])
    assert all(r['offline_analysis']['parse_bozo'] for r in report['routes'])
    assert not report['coverage_complete']


def test_explicit_processing_truncation_cannot_claim_complete_coverage(capture):
    session=capture.run()
    session['summary']['source_diagnostics'][0]['processing_truncated']=True
    report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert not report['coverage_complete']


def test_profile_is_explicit_frozen_and_rejects_old_eight_route_capture(capture):
    from dataclasses import FrozenInstanceError
    assert PROFILE.production=='e5c5ad60a99d0b2128a05ce5d3f418bf2b7e9a98'
    assert PROFILE.urls==EXPECTED and len(PROFILE.issuer_pairs)==4
    with pytest.raises(FrozenInstanceError):PROFILE.urls=('https://unapproved.invalid',)
    session=capture.run()
    session['schema']='ross.primary_feed_diagnostic.v1'
    session['profile']='ross_primary_feed_diagnostic'
    with pytest.raises(ValueError,match='Invalid or incomplete'):DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    with pytest.raises(SystemExit):DIAGNOSTIC.main(entry.__file__,['--urls','https://unapproved.invalid'])


def test_two_simultaneous_shared_fetches_never_expand_to_four_issuer_requests(capture,monkeypatch):
    from src.news import issuer_rss_queries
    monkeypatch.setattr(issuer_rss_queries,'operational_queries',lambda *a:pytest.fail('Issuer query attempted'))
    active=[0];peak=[0];lock=threading.Lock();both=threading.Event();seen=[]
    def get(url,**kwargs):
        assert url in EXPECTED and kwargs['allow_redirects'] is False
        with lock:
            active[0]+=1;peak[0]=max(peak[0],active[0]);seen.append(url)
            if active[0]==2:both.set()
        try:
            assert both.wait(2),'Expected both fixed requests to share one wave'
            return Response(xml(item()))
        finally:
            with lock:active[0]-=1
    monkeypatch.setattr(d.fetcher.requests,'get',get)
    session=capture.run();report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert sorted(seen)==sorted(EXPECTED) and peak[0]==2 and active[0]==0
    assert report['limits']['max_concurrent_requests']==2
    assert report['limits']['max_bodies']==2 and report['limits']['max_raw_bytes']==1048576
    assert report['limits']['supervisor_seconds']==45
    assert set(report['issuers'])=={'AZTR','RENT','GCTK','SPRC'}


def test_parser_recovery_never_qualifies_recovered_article(capture,monkeypatch):
    monkeypatch.setattr(d.fetcher.requests,'get',lambda *a,**kw:Response(xml(item())[:-6]))
    session=capture.run();report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert not report['coverage_complete']
    for route in report['routes']:
        assert route['parsing_status']=='parser_recovery' and not route['adjudicable']
        analysis=route['offline_analysis']
        assert analysis['parsed_entry_count']==analysis['unassessed_parser_entries']==1
        assert analysis['entries_examined']==0 and analysis['samples']=={}


def test_worker_hidden_mode_cannot_write_into_source(monkeypatch):
    monkeypatch.setattr(DIAGNOSTIC,'identity',lambda expected:SOURCE)
    with pytest.raises(ValueError,match='empty directory outside'):
        DIAGNOSTIC.worker(NS(output=d.ROOT,acquire=True,expected_commit='a'*40))


@pytest.mark.parametrize('body',[
    b'<rss version="2.0"><channel><title>Empty</title></channel></rss>',
    b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty</title></feed>',
])
def test_recognized_empty_reports_access_and_parsing_without_qualifying_news(capture,monkeypatch,body):
    monkeypatch.setattr(d.fetcher.requests,'get',lambda *a,**kw:Response(body))
    session=capture.run();report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    assert report['coverage_complete'] and report['no_operational_publication']
    for route in report['routes']:
        assert route['access_status']=='http_success' and route['parsing_status']=='recognized_feed'
        assert route['offline_analysis']['entries_examined']==0
        assert not any(route['offline_analysis']['qualification_counts_by_issuer'].values())
    assert report['PAPER_READY']=='NO' and report['PAPER_READINESS_GATE']=='FAIL'


def test_atom_publication_qualification_is_diagnostic_only(capture,monkeypatch):
    data=b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Offline</title>
      <entry><id>urn:synthetic</id><title>Azitra Inc reports earnings beat</title>
      <published>2026-10-26T18:59:00Z</published><link href="https://synthetic.invalid/a"/></entry></feed>'''
    monkeypatch.setattr(d.fetcher.requests,'get',lambda *a,**kw:Response(data))
    session=capture.run();report=DIAGNOSTIC.build_report(capture.private,session,SOURCE)
    for route in report['routes']:
        analysis=route['offline_analysis']
        assert analysis['qualification_is_diagnostic_only']
        assert analysis['freshness_counts']['current']==1
        assert analysis['qualification_counts_by_issuer']['AZTR']=={'qualified':1}
        sample=analysis['samples']['matched'][0]
        assert sample['timestamp_provenance']['published_utc']=='2026-10-26T18:59:00+00:00'
        assert sample['issuer_decisions']['AZTR']['age_seconds']==60
    assert report['authority']=='diagnostic_only_not_natural_acceptance' and report['PAPER_READY']=='NO'


def test_replay_uses_shared_rss_validator_instead_of_inventing_format_acceptance(monkeypatch):
    calls=[]
    def reject(feed):
        calls.append(feed)
        raise d.fetcher.RssFeedFormatError('synthetic unrecognized format')
    monkeypatch.setattr(d.fetcher,'_validate_feed',reject)
    analysis=DIAGNOSTIC.adjudicate(xml(item()),NOW.isoformat())
    assert len(calls)==1 and not analysis['recognized_feed']
    assert analysis['entries_examined']==0 and analysis['unassessed_parser_entries']==1
    assert analysis['validation_error_code']=='RSSFEEDFORMATERROR'
