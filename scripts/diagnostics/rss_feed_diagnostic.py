"""Shared bounded RSS diagnostic components extracted from reviewed PR1132 e10089a5.

Scope is an explicit immutable caller profile, not mutable globals or CLI URLs.
Acquisition/capture/parsing/qualification/privacy use their existing src owners.

Live acquisition is explicit. Private raw bodies are never added to the shareable
ZIP. Replay requires original hashes/clock and does not invoke any transport.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ibkr.evidence_safety import sanitize, scan_artifacts, write_json
from src.news import news_fetcher as fetcher
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest
from src.news.rss_exclusion_evidence import retain_exclusion, SAMPLES_PER_REASON
from src.news.rss_lifecycle import RssFetchLifecycle
from src.news.rss_raw_capture import RAW_FEED_BYTES
# The established policy facade imports configuration/type dependencies. They
# must not print operator configuration before the sanitized CLI boundary.
with open(os.devnull, 'w') as _quiet, redirect_stdout(_quiet), redirect_stderr(_quiet):
    from src.strategies.ross_momentum.policy import catalyst_policy as catalyst

BUDGET, REQUEST_CAP, CLEANUP, SUPERVISOR = 8., 5., 10., 45.


@dataclass(frozen=True)
class DiagnosticProfile:
    name: str
    schema: str
    production: str
    urls: tuple[str, ...]
    issuer_pairs: tuple[tuple[str, str], ...]
    archive_name: str

    def __post_init__(self):
        if (not 1 <= len(self.urls) <= 8 or len(set(self.urls)) != len(self.urls)
                or len(dict(self.issuer_pairs)) != len(self.issuer_pairs)
                or Path(self.archive_name).name != self.archive_name
                or not self.archive_name.endswith('.zip')):
            raise ValueError('Invalid diagnostic profile')


class RssFeedDiagnostic:
    def __init__(self, profile: DiagnosticProfile):
        self.profile = profile

    @property
    def issuers(self):
        return dict(self.profile.issuer_pairs)

    def identity(self, expected):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(ROOT), *args], timeout=5, text=True).strip()
        head = git('rev-parse', 'HEAD')
        if head != expected or len(expected) != 40:
            raise ValueError('Exact source head mismatch')
        if git('status', '--porcelain'):
            raise ValueError('Pinned checkout must be clean, including untracked files')
        subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', self.profile.production, head],
                       check=True, timeout=5, capture_output=True)
        return {'head': head, 'tree': git('rev-parse', 'HEAD^{tree}'), 'production_base': self.profile.production}

    def new_output(self, path, replay=None):
        original = Path(path)
        path = original.resolve()
        if original.is_symlink() or path == ROOT or ROOT in path.parents or path.exists():
            raise ValueError('Output must be new and outside the source checkout')
        if replay and (path == Path(replay).resolve() or path in Path(replay).resolve().parents
                       or Path(replay).resolve() in path.parents):
            raise ValueError('Replay input/output must be disjoint')
        path.mkdir(parents=True)
        return path

    def fetch_batch(self, lifecycle, raw):
        # Exactly one shared schedule for all four issuers. No store/service/scanner.
        return fetcher.fetch_headlines_for_symbols(list(self.issuers), list(self.profile.urls), lookback_hours=6,
            request_timeout_s=REQUEST_CAP, total_news_budget_seconds=BUDGET,
            symbol_metadata={s: {'company_name': name} for s, name in self.issuers.items()},
            max_entries_per_symbol=5, source_tier='operational_query',
            source_groups_by_url={url: 'DIAGNOSTIC_CANDIDATE' for url in self.profile.urls},
            retention_selector=catalyst.select_qualification_evidence,
            retention_request=NewsRequest(max_evidence_per_symbol=6, metadata={'presentation_limit': 5}),
            lifecycle=lifecycle, raw_feed_directory=raw)

    def acquire(self, private, source):
        lifecycle = RssFetchLifecycle()
        original = fetcher.requests.get
        deadline = time.monotonic() + BUDGET
        attempts, lock = {}, threading.Lock()
        def scoped_get(url, **kwargs):
            if url not in self.profile.urls:
                raise ValueError('Out-of-scope HTTP destination')
            with lock:
                if url in attempts:
                    raise ValueError('Repeated transport attempt is forbidden')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Shared acquisition deadline exhausted')
                effective = min(float(kwargs['timeout']), REQUEST_CAP, remaining)
                attempts[url] = {'timeout_seconds': effective, 'remaining_budget_seconds': remaining}
            timing = fetcher.current_source_timing()
            if timing is not None:
                timing['_cancel'] = lambda: time.monotonic() >= deadline
            # Requests' default redirect following could silently escape the URL list.
            return original(url, **dict(kwargs, timeout=effective, allow_redirects=False))
        fetcher.requests.get = scoped_get
        summary, error = None, None
        try:
            _, result = self.fetch_batch(lifecycle, private / 'raw')
            summary = asdict(result)
        except Exception as exc:
            error = type(exc).__name__  # Never persist arbitrary exception text.
        finally:
            cleanup = lifecycle.wait_for_cleanup(CLEANUP)
            fetcher.requests.get = original
        session = {'schema': self.profile.schema, 'profile': self.profile.name, 'source': source, 'urls': list(self.profile.urls), 'issuers': self.issuers,
                   'summary': summary, 'cleanup': cleanup, 'acquisition_error': error,
                   'transport_attempts': attempts}
        # No read/packaging of sidecars while an owned worker might still write.
        if not cleanup['cleanup_complete']:
            write_json(private / 'session.json', session)
            raise RuntimeError('Owned RSS workers did not stop within cleanup bound')
        records = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((private/'raw').glob('*.json'))]
        clocks = {r['evaluation_time_utc'] for r in records}
        if len(clocks) > 1 or None in clocks:
            raise ValueError('Inconsistent capture evaluation clock')
        session['evaluation_time_utc'] = next(iter(clocks), None)
        write_json(private / 'session.json', session)
        return session


    @contextmanager
    def recorded_clock(self, stamp):
        when = datetime.fromisoformat(stamp)
        if when.tzinfo is None:
            raise ValueError('Capture clock must be timezone-aware')
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(when.timestamp(), tz)
        proxy = SimpleNamespace(time=lambda: when.timestamp(), monotonic=time.monotonic)
        old = (fetcher.datetime, fetcher.time, catalyst.time)
        fetcher.datetime, fetcher.time, catalyst.time = Clock, proxy, proxy
        try:
            yield when.timestamp()
        finally:
            fetcher.datetime, fetcher.time, catalyst.time = old

    def load_capture(self, private, session):
        if (session.get('schema') != self.profile.schema or session.get('profile') != self.profile.name or session.get('urls') != list(self.profile.urls)
                or session.get('issuers') != self.issuers or not session.get('cleanup', {}).get('cleanup_complete')):
            raise ValueError('Invalid or incomplete private session')
        records = {}
        for url in self.profile.urls:
            key = hashlib.sha256(url.encode()).hexdigest()
            manifest = private/'raw'/(key+'.json')
            if not manifest.exists():
                continue
            if manifest.is_symlink() or manifest.stat().st_size > 16384:
                raise ValueError('Unsafe raw manifest')
            record = json.loads(manifest.read_text(encoding='utf-8'))
            if (record['url'] != url or record['body_file'] != key+'.xml'
                    or record['evaluation_time_utc'] != session['evaluation_time_utc']
                    or record['byte_limit'] != RAW_FEED_BYTES):
                raise ValueError('Raw manifest identity mismatch')
            body = private/'raw'/record['body_file']
            if body.is_symlink() or body.stat().st_size > RAW_FEED_BYTES:
                raise ValueError('Unsafe/oversize raw body')
            data = body.read_bytes()
            if len(data) != record['bytes_captured'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Raw capture hash/length mismatch')
            records[url] = (record, data)
        actual = {p.name for p in (private/'raw').iterdir()} if (private/'raw').exists() else set()
        expected = {hashlib.sha256(url.encode()).hexdigest()+ext for url in records for ext in ('.json','.xml')}
        if actual != expected or len(records) > len(self.profile.urls):
            raise ValueError('Unexpected raw capture inventory')
        return records

    def entry_decisions(self, entry, now):
        title = fetcher._clean_text(fetcher._entry_value(entry, 'title'))
        summary = fetcher._entry_summary(entry)
        url = fetcher._clean_text(fetcher._entry_value(entry, 'link'))
        stamp, dates = fetcher._entry_date_facts(entry)
        reason = ('missing_title' if not title else 'missing_publication_time' if stamp is None
                  else 'future_publication_time' if stamp > now else 'outside_lookback_window'
                  if stamp < now-21600 else None)
        decisions = {}
        for symbol, name in self.issuers.items():
            match = fetcher.symbol_relevance_match(symbol, title=title, summary=summary,
                                                   metadata={'company_name': name})
            decision = {'match': list(match) if match else None, 'qualified': False,
                        'reason': reason or 'issuer_match_unverified'}
            if reason is None and match:
                item = fetcher.Headline(title, '', stamp, url, summary=summary,
                    source_tier='operational_query', company_name=name, timestamp_provenance=dates)
                decision.update(catalyst.assess_issuer_event(symbol, item, (NewsCandidate(symbol, company_name=name),)))
            decisions[symbol] = decision
        group = reason or ('matched' if any(d['match'] for d in decisions.values()) else 'issuer_match_unverified')
        return title, summary, url, dates, group, decisions

    def adjudicate(self, data, stamp):
        """Offline diagnostic over captured items; never publishes canonical articles."""
        feed = fetcher.feedparser.parse(data)
        counts, per_issuer, samples = Counter(), {s: Counter() for s in self.issuers}, {}
        qualified = {s: Counter() for s in self.issuers}
        validation_error, recognized = None, True
        try:
            fetcher._validate_feed(feed)  # Same accepted parsing authority, not a second rule.
        except fetcher.RssFeedParseError as exc:
            validation_error = fetcher._failure_code(exc)
        except fetcher.RssFeedFormatError as exc:
            validation_error, recognized = fetcher._failure_code(exc), False
        valid = validation_error is None
        with self.recorded_clock(stamp) as now:
            for index, entry in enumerate(feed.entries if valid else [], 1):
                title, summary, url, dates, group, decisions = self.entry_decisions(entry, now)
                counts[group] += 1
                for symbol, decision in decisions.items():
                    per_issuer[symbol][decision['reason']] += 1
                    qualified[symbol]['qualified' if decision['qualified'] else 'rejected'] += 1
                rows = samples.setdefault(group, [])
                if len(rows) < SAMPLES_PER_REASON:
                    carrier = {}
                    # Reuse the exact sanitizer/clip/hash implementation for text.
                    # 'matched' is a report bucket, not an exclusion reason/authority.
                    retain_exclusion(carrier, reason='issuer_match_unverified' if group == 'matched' else group,
                        entry_index=index, title=title, summary=summary, url=url, date_facts=dates)
                    record = carrier['exclusion_evidence']['samples'][
                        'issuer_match_unverified' if group == 'matched' else group][0]
                    record.update(reason=group, issuer_decisions=sanitize(decisions))
                    rows.append(record)
        return {'parsed_entry_count': len(feed.entries), 'unassessed_parser_entries': len(feed.entries) if not valid else 0,
            'qualification_is_diagnostic_only': True,
            'qualification_counts_by_issuer': {s: dict(v) for s, v in qualified.items()},
            'freshness_counts': {'current': counts['matched'] + counts['issuer_match_unverified'],
                                 'stale': counts['outside_lookback_window'], 'future': counts['future_publication_time'],
                                 'unknown_time': counts['missing_publication_time'],
                                 'not_assessed_missing_title': counts['missing_title']},
            'validation_error_code': validation_error, 'entries_examined': sum(counts.values()), 'counts': dict(counts),
                'per_issuer_reason_counts': {s: dict(v) for s,v in per_issuer.items()},
                'samples': samples, 'samples_per_reason': SAMPLES_PER_REASON,
                'omitted_samples': {g: n-len(samples[g]) for g,n in counts.items()},
                'parse_bozo': bool(feed.get('bozo')), 'recognized_feed': recognized,
                'parse_error_type': type(feed.get('bozo_exception')).__name__ if feed.get('bozo') else None,
                'counts_are_entry_observations_not_unique_articles': True,
                'sampled_coverage_is_exhaustive': False}

    def build_report(self, private, session, source):
        if session.get('source') != source:
            raise ValueError('Capture and replay must use the same exact source identity')
        if private.is_symlink() or (private/'raw').is_symlink():
            raise ValueError('Private capture directories must not be symlinks')
        captures = self.load_capture(private, session)
        diagnostics = {r['source_id']: r for r in (session.get('summary') or {}).get('source_diagnostics', [])}
        rows = []
        for url in self.profile.urls:
            diag = diagnostics.get(url, {})
            row = {'url': url, 'attempted': bool(diag.get('attempted')),
                   'acquisition_status': diag.get('retrieval_status', 'unattempted'),
                   'transport_invoked': url in session.get('transport_attempts', {}),
                   'transport_budget': session.get('transport_attempts', {}).get(url),
                   'failure_reason': diag.get('failure_reason'),
                   'timeout_seconds': diag.get('timeout_seconds'),
                   'processing_truncated': diag.get('processing_truncated', False),
                   'acquisition_entries_examined': diag.get('entries_examined_count'),
                   'acquisition_date_and_match_counts': {k: v for k, v in diag.get('entry_diagnostics', {}).items()
                       if k in ('within_window', 'missing_invalid_dates', 'stale_entries', 'future_entries',
                                'relevance_rejections_by_symbol')},
                   'raw_capture_present': url in captures, 'adjudicable': False, 'access_status': 'unattempted' if not diag.get('attempted') else 'no_response_capture',
               'parsing_status': 'not_adjudicated'}
            if url in captures:
                record, data = captures[url]
                row['capture'] = {k: record[k] for k in ('acquired_at','evaluation_time_utc','http_status',
                    'bytes_captured','byte_limit','body_complete','sha256','error')}
                code = record['http_status']
                row['access_status'] = ('redirect_unfollowed' if code is not None and 300 <= code < 400
                                        else 'http_success' if code == 200 else 'http_error' if code is not None else 'no_response')
                row['parsing_status'] = 'incomplete_body' if not record['body_complete'] else 'not_adjudicated_access_failure'
                row['adjudicable'] = bool(record['body_complete'] and record['http_status'] == 200 and not record['error'])
                if row['adjudicable']:
                    row['offline_analysis'] = self.adjudicate(data, session['evaluation_time_utc'])
                    analysis = row['offline_analysis']
                    row['parsing_status'] = ('unrecognized_feed' if not analysis['recognized_feed']
                                             else 'parser_recovery' if analysis['parse_bozo'] else 'recognized_feed')
                    row['adjudicable'] = analysis['recognized_feed'] and not analysis['parse_bozo']
                    # Post-deadline raw bodies are facts only, never in-budget evidence.
                    row['analysis_scope'] = 'captured_body_replay_not_admission_or_in_budget_completion'
            rows.append(row)
        return {'schema': self.profile.schema, 'profile': self.profile.name, 'authority': 'diagnostic_only_not_natural_acceptance',
            'source': source, 'capture_source': session['source'], 'issuers': self.issuers,
            'matching_aliases': {s: list(fetcher.company_aliases_for_symbol(s, {'company_name': n}))
                                 for s, n in self.issuers.items()},
            'evaluation_time_utc': session.get('evaluation_time_utc'),
            'limits': {'acquisition_seconds': BUDGET, 'request_seconds_cap': REQUEST_CAP,
                       'cleanup_seconds': CLEANUP, 'supervisor_seconds': SUPERVISOR, 'lookback_seconds': 21600,
                       'max_concurrent_requests': min(fetcher.DEFAULT_RSS_FETCH_WORKERS, len(self.profile.urls)),
                       'max_bodies': len(self.profile.urls), 'bytes_per_body': RAW_FEED_BYTES, 'max_raw_bytes': len(self.profile.urls)*RAW_FEED_BYTES},
            'acquisition_error': session.get('acquisition_error'), 'cleanup': session['cleanup'],
            'raw_body_count': len(captures),
            'raw_bytes_total': sum(len(data) for _, data in captures.values()),
            'routes': rows, 'coverage_complete': all(
                r['adjudicable'] and r['acquisition_status']=='available'
                and not r['processing_truncated'] and not r['offline_analysis']['parse_bozo']
                for r in rows),
            'no_operational_publication': True, 'PAPER_READY': 'NO', 'PAPER_READINESS_GATE': 'FAIL'}

    def package(self, output, report):
        share = output/'shareable'
        share.mkdir()
        write_json(share/'report.json', report)
        privacy = scan_artifacts(share)
        write_json(share/'privacy.json', privacy)
        if not privacy['passed'] or not scan_artifacts(share)['passed']:
            raise ValueError('Shareable privacy verification failed')
        archive = output/self.profile.archive_name
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
            for name in ('report.json', 'privacy.json'):
                z.write(share/name, name)
        # Verify the actual ZIP members after packaging; raw is never an input.
        with zipfile.ZipFile(archive) as z:
            if z.namelist() != ['report.json', 'privacy.json']:
                raise ValueError('Unexpected shareable inventory')
            for name in z.namelist():
                if z.read(name) != (share/name).read_bytes():
                    raise ValueError('Shareable member mismatch')
        return hashlib.sha256(archive.read_bytes()).hexdigest()

    def worker(self, args):
        source = self.identity(args.expected_commit)
        output = args.output.resolve()
        if output == ROOT or ROOT in output.parents or not output.is_dir() or any(output.iterdir()):
            raise ValueError('Worker output must be an empty directory outside source')
        private = output/'private'
        if args.acquire:
            private.mkdir(mode=0o700)
            session = self.acquire(private, source)
        else:
            private = args.replay.resolve()
            manifest = private/'session.json'
            if manifest.is_symlink() or manifest.stat().st_size > 1024*1024:
                raise ValueError('Unsafe session manifest')
            session = json.loads(manifest.read_text(encoding='utf-8'))
        report = self.build_report(private, session, source)
        report['source_unchanged'] = self.identity(args.expected_commit) == source
        report['mode'] = 'acquisition' if args.acquire else 'offline_replay'
        digest = self.package(args.output, report)
        return {'exit': 0 if report['coverage_complete'] else 2, 'archive_sha256': digest}

    def main(self, entrypoint, argv=None):
        parser = argparse.ArgumentParser(description=(self.profile.name + ': exactly ' +
            str(len(self.profile.urls)) + ' shared URLs: ' + ', '.join(self.profile.urls)))
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--acquire', action='store_true')
        mode.add_argument('--replay', type=Path, help='Private directory containing session.json and raw/')
        parser.add_argument('--output', type=Path, required=True)
        parser.add_argument('--expected-commit', required=True)
        parser.add_argument('--_worker', action='store_true', help=argparse.SUPPRESS)
        args = parser.parse_args(argv)
        if args._worker:
            with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
                result = self.worker(args)
            return result['exit']
        source_before = self.identity(args.expected_commit)
        args.output = self.new_output(args.output, args.replay)
        command = [sys.executable, '-I', '-B', str(Path(entrypoint).resolve()), '--_worker',
                   '--output', str(args.output), '--expected-commit', args.expected_commit]
        command += ['--acquire'] if args.acquire else ['--replay', str(args.replay.resolve())]
        try:
            completed = subprocess.run(command, timeout=SUPERVISOR, capture_output=True)
            status = completed.returncode
        except subprocess.TimeoutExpired:
            status = 1  # Child is killed/waited; no worker can continue acquiring.
        archive = args.output/self.profile.archive_name
        if status not in (0, 2):
            failure = args.output/'failure'
            failure.mkdir()
            self.package(failure, {'schema': self.profile.schema, 'profile': self.profile.name,
                'source_before': source_before, 'planned_urls': list(self.profile.urls),
                'status': 'worker_failed_or_timed_out',
                'coverage_complete': False, 'source_unchanged': 'not_verified',
                'PAPER_READY': 'NO', 'PAPER_READINESS_GATE': 'FAIL'})
            archive = failure/self.profile.archive_name
            status = 1
        print(json.dumps({'exit': status, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                          'shareable_zip': str(archive), 'raw_bodies_private': True}))
        return status
