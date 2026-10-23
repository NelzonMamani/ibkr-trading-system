"""Bounded native quote transport facts; never quote/entitlement authority.

No prices, account data, error text or arbitrary callback payloads are retained.
SDK return is deliberately distinct from broker receipt/acknowledgement.
"""
from collections import OrderedDict
from datetime import datetime, timezone
import json
import sys
from importlib.metadata import PackageNotFoundError, version
import threading

from src.ibkr.evidence_safety import sanitize


class QuoteDiagnostics:
    MAX_REQUESTS = 128
    MAX_LOGS = 512
    MAX_LOG_BYTES = 8192
    TICK_TYPES = frozenset((0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 14, 45, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 88))
    MAX_COUNT = 2**31 - 1
    KINDS = {'marketDataType', 'tickPrice', 'tickSize', 'tickString', 'tickSnapshotEnd', 'error'}
    REASONS = {'accepted', 'unknown_request', 'inactive', 'wrong_owner', 'conflicted',
               'missing_ticker', 'unsupported_tick', 'invalid_value'}

    def __init__(self, client_id):
        self.client_id = client_id
        self.requests = OrderedDict()
        self.logs = 0
        self.suppressed_logs = 0
        self.evicted_requests = 0
        self.unknown_callbacks = {}
        self._lock = threading.RLock()
        try:
            sdk_version = version('ibapi')
        except PackageNotFoundError:
            sdk_version = 'UNKNOWN'
        self._emit('environment', None, {'python': sys.version.split()[0],
            'ibapi_distribution': self._text(sdk_version), 'transport': 'native_ibapi'})

    @staticmethod
    def _text(value):
        text = str(value or '')
        return sanitize(text) if len(text) <= 64 else 'OVERSIZE_REDACTED'

    def _emit(self, event, req_id, facts):
        if self.logs >= self.MAX_LOGS:
            self.suppressed_logs = min(self.MAX_COUNT, self.suppressed_logs + 1)
            return
        if self.logs == self.MAX_LOGS - 1:
            event, facts = 'logging_limit_reached', {'max_logs': self.MAX_LOGS,
                'max_retained_requests': self.MAX_REQUESTS, 'later_events_not_logged': True}
        self.logs += 1
        row = {'event': event, 'client_id': self.client_id, 'req_id': req_id,
               'utc': datetime.now(timezone.utc).isoformat(),
               'evicted_requests': self.evicted_requests,
               'suppressed_logs': self.suppressed_logs, **facts}
        try:
            encoded = json.dumps(sanitize(row), sort_keys=True)
            if len(encoded.encode('utf-8')) > self.MAX_LOG_BYTES:
                encoded = json.dumps({'event': event, 'client_id': self.client_id,
                    'req_id': req_id, 'details_omitted_due_to_size': True})
            print('[IBKR][QUOTE_TRACE] ' + encoded)
        except Exception:
            # Diagnostics cannot change transport/qualification/control flow.
            self.suppressed_logs = min(self.MAX_COUNT, self.suppressed_logs + 1)

    def start(self, req_id, contract, requested_type, generic_ticks, snapshot, regulatory, options):
        with self._lock:
            if len(self.requests) >= self.MAX_REQUESTS:
                self.requests.popitem(last=False)
                self.evicted_requests = min(self.MAX_COUNT, self.evicted_requests + 1)
            row = {'identity': {key: self._text(getattr(contract, key, None)) for key in
                   ('symbol', 'secType', 'exchange', 'primaryExchange', 'currency')},
                   'con_id': int(getattr(contract, 'conId', 0) or 0),
                   'requested_type': requested_type, 'returned_type': None,
                   'generic_ticks': self._text(generic_ticks), 'snapshot': bool(snapshot),
                   'regulatory_snapshot': bool(regulatory), 'option_count': len(options or []),
                   'owner': 'MARKET_DATA', 'send_outcome': 'SDK_CALL_PENDING',
                   'callbacks': {}, 'tick_counts': {}, 'completion': 'NOT_RECORDED', 'cleanup': None}
            self.requests[req_id] = row
            self._emit('request', req_id, {k: v for k, v in row.items() if k != 'callbacks'})

    def sent(self, req_id, outcome):
        with self._lock:
            row = self.requests.get(req_id)
            if row is not None:
                row['send_outcome'] = outcome
                self._emit('send', req_id, {'outcome': outcome, 'broker_receipt_verified': False})

    def callback(self, req_id, kind, reason, *, owner=None, returned_type=None, tick_type=None):
        assert kind in self.KINDS and reason in self.REASONS
        with self._lock:
            row = self.requests.get(req_id)
            counts = row['callbacks'] if row is not None else self.unknown_callbacks
            key = kind + ':' + reason
            if row is not None and tick_type is not None:
                bucket = str(tick_type) if tick_type in self.TICK_TYPES else 'OTHER'
                tick_key = bucket + (':accepted' if reason == 'accepted' else ':rejected')
                row['tick_counts'][tick_key] = min(self.MAX_COUNT, row['tick_counts'].get(tick_key, 0) + 1)
            first = key not in counts
            counts[key] = min(self.MAX_COUNT, counts.get(key, 0) + 1)
            if row is not None and returned_type is not None and reason == 'accepted':
                row['returned_type'] = returned_type if returned_type in (1, 2, 3, 4) else None
            if first:
                self._emit('callback', req_id, {'kind': kind, 'reason': reason,
                    'accepted': reason == 'accepted',
                    'tick_type': tick_type if tick_type in self.TICK_TYPES else 'OTHER',
                    'owner': owner if owner in ('MARKET_DATA', 'HISTORICAL_DATA', 'CONTRACT_DETAILS', 'SCANNER_DATA') else 'OTHER_OR_NONE',
                    'returned_type': returned_type if returned_type in (1, 2, 3, 4) else None})

    def finish(self, req_id, reason):
        with self._lock:
            row = self.requests.get(req_id)
            if row is not None:
                row['completion'] = reason
                self._emit('completion', req_id, {'reason': reason, 'callbacks': dict(row['callbacks']),
                    'requested_type': row['requested_type'], 'returned_type': row['returned_type'],
                    'tick_counts': dict(row['tick_counts'])})

    def cleanup(self, req_id, outcome, *, active, ticker_present, event_present):
        with self._lock:
            row = self.requests.get(req_id)
            if row is not None:
                row['cleanup'] = {'cancel_outcome': outcome, 'active_after': active,
                    'ticker_present_after': ticker_present, 'event_present_after': event_present,
                    'broker_cancel_acknowledged': False}
                self._emit('cleanup', req_id, row['cleanup'])
