"""Runtime-owned, broker-free bounded maintenance of the canonical news service.

Workers acquire one issuer at a time and publish through the existing service's
serialized store owner. Consumers read completed issuer results immediately.
"""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import threading
import time

from src.config.config_resolver import get_config
from src.core.acquisition import acquisition_scope, AcquisitionCancelled, checkpoint, _file_stop
from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.feed_pool import SharedFeedPool
from src.news.news_intelligence_contract import NewsBatchResult, RetrievalDiagnostics
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.rss_lifecycle import RssFetchLifecycle


def _stable(value):
    if callable(value):
        return value.__module__+'.'+value.__qualname__
    if isinstance(value, dict):
        return {key: _stable(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)):
        return [_stable(item) for item in value]
    return value


def identity(candidate):
    return (candidate.normalized_symbol, str(candidate.company_name or '').strip().upper(),
            tuple(sorted(str(alias).strip().upper() for alias in candidate.aliases)),
            candidate.exchange, candidate.market, candidate.region,
            json.dumps([candidate.metadata.get("security_identifiers"),candidate.metadata.get("issuer_identifiers")],sort_keys=True,default=str))


def effective_policy(policy):
    return replace(policy,total_budget_seconds=min(8.,float(policy.total_budget_seconds or 8.)),
                   refresh_interval_seconds=(policy.refresh_interval_seconds if policy.refresh_interval_seconds is not None
                                             else float(get_config("NEWS_REFRESH_SECONDS_RTH") or 120.)))


def request_key(candidate, request, policy):
    # Market attention and queue priority are not issuer/query identity.
    issuer = identity(candidate)
    profile = _stable({'request':asdict(request),'policy':asdict(effective_policy(policy))})
    return hashlib.sha256(json.dumps([issuer,profile],sort_keys=True,default=str).encode()).hexdigest()


@dataclass
class Work:
    key: str
    candidate: object
    request: object
    policy: object
    sequence: int
    priority: int = 2
    due: float = 0.
    running: bool = False
    failures: int = 0
    completed: int = 0


class NewsMaintenance:
    def __init__(self, *, store=None, service_factory=None, workers=2, capacity=128,
                 stop_requested=None, clock=time.monotonic):
        if not 1 <= workers <= 2 or not 1 <= capacity <= 256:
            raise ValueError('news maintenance bounds')
        self.store = store or CanonicalNewsEvidenceStore()
        self.clock, self.capacity, self.worker_limit = clock, capacity, workers
        self.stop = threading.Event()
        self.external_stop = stop_requested or (lambda:False)
        feed_cadence = float(get_config("NEWS_REFRESH_SECONDS_RTH") or 120.)
        self.feeds = SharedFeedPool(stop=self.stop, stop_requested=self.stopped,
                                    ttl=feed_cadence, failure_backoff=feed_cadence)
        self.factory = service_factory or self._service
        self.condition = threading.Condition()
        self.work = {}
        self.threads = []
        self.sequence = 0
        self.active_streak = 0
        self.stats = {'submitted':0,'deduplicated':0,'rejected_full':0,'completed':0,'failed':0,'retired':0,'publication_failures':0}
        self.receipts = []
        self.started_at = None
        self.first_result_seconds = None
        self.first_evidence_seconds = None
        self.lifecycles = []
        self.universe = None
        self.active = set()

    def _service(self):
        return CanonicalNewsIntelligenceService(evidence_store=self.store,
            retrieval_provider=BatchRssNewsIntelligenceProvider(lifecycle=RssFetchLifecycle(),feed_pool=self.feeds))

    def _event(self, name, **fields):
        print('[NEWS][MAINTENANCE]['+name+'] '+json.dumps({
            'utc':datetime.now(timezone.utc).isoformat(),**fields}),flush=True)

    def stopped(self):
        return self.stop.is_set() or self.external_stop() or _file_stop()

    def submit(self, candidates, request, policy, *, priority=2):
        accepted = 0
        policy = effective_policy(policy)
        with self.condition:
            if self.stopped():
                return 0
            for candidate in sorted(candidates,key=lambda row:(row.priority_rank is None,row.priority_rank or 0,row.normalized_symbol)):
                key = request_key(candidate,request,policy)
                if key in self.work:
                    self.stats['deduplicated'] += 1
                    self.work[key].candidate = candidate
                    self.work[key].priority = min(priority,self.work[key].priority)
                    continue
                if len(self.work) >= self.capacity:
                    self.stats['rejected_full'] += 1
                    continue
                self.sequence += 1
                self.work[key] = Work(key,candidate,request,policy,self.sequence,priority)
                self.stats['submitted'] += 1
                accepted += 1
            self._event('QUEUE',accepted=accepted,**self.snapshot())
            if accepted and not self.threads:
                self.started_at = self.clock()
                self.threads = [threading.Thread(target=self._run,name=f'news-maintenance-{i}',daemon=False)
                                for i in range(self.worker_limit)]
                for thread in self.threads:
                    thread.start()
            self.condition.notify_all()
        return accepted

    def set_universe(self, symbols):
        with self.condition:
            self.universe = set(symbols)
            previous = len(self.work)
            self.work = {key:item for key,item in self.work.items()
                         if item.candidate.normalized_symbol in self.universe | self.active or item.running}
            self.stats['retired'] += previous-len(self.work)

    def set_active(self, watchlist=(), focus=()):
        watch, focused = set(watchlist), set(focus)
        with self.condition:
            self.active = watch | focused
            for item in self.work.values():
                symbol = item.candidate.normalized_symbol
                item.priority = 0 if symbol in focused else 1 if symbol in watch else 2
            self._event('PRIORITY',watchlist=sorted(watch),focus=sorted(focused),
                        fairness_active_dispatch_limit=3,**self.snapshot())
            self.condition.notify_all()

    def _take(self):
        now = self.clock()
        running = {identity(item.candidate) for item in self.work.values() if item.running}
        ready = [item for item in self.work.values() if not item.running and item.due <= now
                 and identity(item.candidate) not in running]
        if not ready:
            return None
        # At most three active dispatches before the oldest waiting normal row.
        normal = [item for item in ready if item.priority == 2]
        fairness = bool(normal and self.active_streak >= 3)
        if fairness:
            chosen = min(normal,key=lambda item:(item.due,item.sequence))
        else:
            chosen = min(ready,key=lambda item:(item.priority,item.due,item.sequence))
        self.active_streak = self.active_streak+1 if chosen.priority < 2 else 0
        chosen.running = True
        self._event('DISPATCH',symbol=chosen.candidate.normalized_symbol,key=chosen.key,
                    priority=chosen.priority,reason='normal_fairness' if fairness else 'priority_due_order',
                    normal_ready=len(normal),dispatch_ready=len(ready),active_streak=self.active_streak,
                    refresh_interval_seconds=chosen.policy.refresh_interval_seconds,**self.snapshot())
        return chosen

    def _run(self):
        while not self.stopped():
            with self.condition:
                item = self._take()
                if item is None:
                    self.condition.wait(.1)
                    continue
            started = self.clock()
            self._event('LOOKUP_START',symbol=item.candidate.normalized_symbol,key=item.key)
            lifecycle = None
            outcome, error = None, None
            try:
                service = self.factory()
                lifecycle = getattr(service.retrieval_provider,'_lifecycle',None)
                provider = service.retrieval_provider
                class RecordingProvider:
                    provider_id = getattr(provider,'provider_id','unknown')
                    def get_news(self,candidates,request,policy):
                        try:
                            return provider.get_news(candidates,request,policy)
                        except Exception as exc:
                            return NewsBatchResult(candidates=tuple(candidates),request=request,
                                diagnostics=RetrievalDiagnostics(retrieval_status='provider_error',
                                    provider_status='provider_request_failure',provider_available=False,
                                    diagnostics={'failure_reason':type(exc).__name__}))
                # Never mutate an injected/shared service: periodic reuse must
                # not wrap its provider recursively or alter another consumer.
                service = CanonicalNewsIntelligenceService(evidence_store=service.evidence_store,
                                                          retrieval_provider=RecordingProvider())
                if lifecycle is not None:
                    with self.condition:
                        self.lifecycles.append(lifecycle)
                budget = min(8.,float(item.policy.total_budget_seconds or 8.))
                # The existing provider owns the <=8s acquisition deadline.
                # Do not discard its in-budget partial facts merely because local
                # canonical publication/cleanup follows the transport deadline.
                with acquisition_scope(self.stopped):
                    outcome = service.get_news((item.candidate,),item.request,replace(item.policy,total_budget_seconds=budget))
            except AcquisitionCancelled:
                self.stop.set()
            except Exception as exc:
                error = type(exc).__name__
            finally:
                completed_tick = self.clock()
                publication_failed = bool(outcome is not None and outcome.diagnostics.diagnostics.get('cache_write_failed'))
                if publication_failed:
                    error = 'CanonicalPublicationFailed'
                with self.condition:
                    self.stats['publication_failures'] += int(publication_failed)
                    if outcome is not None and not publication_failed and self.first_result_seconds is None:
                        self.first_result_seconds = self.clock()-self.started_at
                    if outcome is not None and not publication_failed and outcome.evidence_for_symbol(item.candidate.normalized_symbol) and self.first_evidence_seconds is None:
                        self.first_evidence_seconds = self.clock()-self.started_at
                published = bool(outcome is not None and not publication_failed and
                                 item.candidate.normalized_symbol in outcome.diagnostics.diagnostics.get('cache_write_symbols',()))
                self._event('PUBLISH' if published else 'LOOKUP_COMPLETE',
                    symbol=item.candidate.normalized_symbol,key=item.key,published=published,
                    elapsed_before_cleanup_seconds=completed_tick-started,error=error,
                    evidence_count=len(outcome.evidence_for_symbol(item.candidate.normalized_symbol)) if outcome else 0,
                    provider_available=outcome.diagnostics.provider_available if outcome else None,
                    budget_exhausted=outcome.diagnostics.budget_exhausted if outcome else None,
                    qualification_evaluated=False,**self.snapshot())
                try:
                    cleanup = lifecycle.wait_for_cleanup(8.) if lifecycle is not None else {'cleanup_complete':True}
                except Exception as exc:
                    cleanup = {'cleanup_complete':False}
                    error = 'Cleanup:' + type(exc).__name__
                with self.condition:
                    if lifecycle is not None and cleanup['cleanup_complete']:
                        self.lifecycles.remove(lifecycle)
                    if not cleanup['cleanup_complete']:
                        self.stop.set()  # Never accumulate abandoned transport workers.
                    failed = error is not None or outcome is None or outcome.diagnostics.unavailable
                    item.running = False
                    item.completed += int(outcome is not None)
                    item.failures = item.failures+1 if failed else 0
                    interval = max(.01,float(item.policy.refresh_interval_seconds or 120.))
                    item.due = completed_tick+interval  # Existing successful/failed acquisition cadence; no rapid retry loop.
                    self.stats['completed'] += int(outcome is not None)
                    self.stats['failed'] += int(failed)
                    elapsed = self.clock()-started
                    if self.universe is not None and item.candidate.normalized_symbol not in self.universe | self.active:
                        self.work.pop(item.key,None)
                    row = {'symbol':item.candidate.normalized_symbol,'elapsed_seconds':elapsed,
                           'error':error,'completed':outcome is not None,'published':outcome is not None and not publication_failed,'cleanup_complete':cleanup['cleanup_complete']}
                    self.receipts.append(row)
                    del self.receipts[:-128]
                    print('[NEWS][MAINTENANCE][RESULT] '+json.dumps(row),flush=True)
                    self.condition.notify_all()

    def read(self, candidates, request, policy):
        # Each issuer's acquisition profile matches its independent worker query.
        reader = CanonicalNewsIntelligenceService(evidence_store=self.store)
        policy = effective_policy(policy)
        evidence, summaries, unresolved = {}, {}, []
        per_symbol, details, outcomes = {}, {}, []
        for candidate in candidates:
            checkpoint()
            result = reader.get_news((candidate,),request,replace(policy,refresh_mode='cache_only',network_allowed=False,allow_cache_write=False))
            symbol = candidate.normalized_symbol
            evidence[symbol] = result.evidence_for_symbol(symbol)
            summaries[symbol] = result.summary_for_symbol(symbol)
            unresolved.extend(result.diagnostics.unresolved_symbols)
            outcome = result.diagnostics
            outcomes.append(outcome)
            per_symbol[symbol] = asdict(outcome)
            for key,value in outcome.diagnostics.items():
                if key.endswith('_by_symbol') and isinstance(value,dict):
                    details.setdefault(key,{}).update(value)
                elif key.endswith('_symbols') and isinstance(value,(list,tuple)):
                    details[key] = list(dict.fromkeys([*details.get(key,()),*value]))
                elif key in ('cache_read_failed','cache_write_failed','prep_read_failed'):
                    details[key] = bool(details.get(key)) or bool(value)
                elif key in ('cache_read_error','cache_write_error','prep_read_error','failure_reason') and value:
                    details.setdefault(key,value)
        unavailable = [row.unavailable for row in outcomes]
        all_failed = bool(outcomes) and all(unavailable)
        statuses = {row.retrieval_status for row in outcomes}
        status = (next(iter(statuses)) if len(statuses)==1 else 'partial') if outcomes else 'not_requested'
        availability = {row.provider_available for row in outcomes}
        available = next(iter(availability)) if len(availability)==1 else None
        cache_states = {row.cache_state for row in outcomes}
        details.update(maintenance=self.snapshot(),maintenance_by_symbol=per_symbol)
        return NewsBatchResult(candidates=tuple(candidates),request=request,retrieval_policy=policy,
            evidence_by_symbol=evidence,summaries_by_symbol=summaries,
            diagnostics=RetrievalDiagnostics(retrieval_status='unavailable' if all_failed else status,
                provider_status=('cache_read_error' if details.get('cache_read_failed') else 'maintenance_cache'),
                provider_available=False if all_failed else available,
                cache_state=next(iter(cache_states)) if len(cache_states)==1 else 'not_checked',
                budget_exhausted=any(row.budget_exhausted for row in outcomes),
                timeout_count=sum(row.timeout_count for row in outcomes),
                unresolved_symbols=tuple(dict.fromkeys(unresolved)),diagnostics=details))

    def snapshot(self):
        with self.condition:
            return {**self.stats,'tracked':len(self.work),'inflight':sum(item.running for item in self.work.values()),
                    'first_result_seconds':self.first_result_seconds,'first_evidence_seconds':self.first_evidence_seconds,'alive_workers':sum(t.is_alive() for t in self.threads),
                    'feed_requests':self.feeds.requests,'feed_reuse':self.feeds.hits,
                    'backlog':sum(not item.running for item in self.work.values()),
                    'ready':sum(not item.running and item.due<=self.clock() for item in self.work.values()),
                    'priority_counts':{str(priority):sum(item.priority==priority for item in self.work.values()) for priority in range(3)}}

    def close(self, timeout=12.):
        self.stop.set()
        with self.condition:
            self.condition.notify_all()
        deadline = time.monotonic()+timeout
        for thread in self.threads:
            thread.join(max(0.,deadline-time.monotonic()))
        with self.condition:
            lifecycles = list(self.lifecycles)
        cleanup_results = []
        for lifecycle in lifecycles:
            try:
                cleanup_results.append(lifecycle.wait_for_cleanup(max(0.,deadline-time.monotonic()))['cleanup_complete'])
            except Exception:
                cleanup_results.append(False)
        cleanup_complete = all(cleanup_results)
        complete = not any(thread.is_alive() for thread in self.threads) and cleanup_complete
        print('[NEWS][MAINTENANCE][SHUTDOWN] '+json.dumps({**self.snapshot(),'cleanup_complete':complete}),flush=True)
        return complete
