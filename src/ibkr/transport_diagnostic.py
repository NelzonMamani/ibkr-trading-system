"""Opt-in, dedicated-process SDK observation. Never changes SDK wire operations.

No raw inbound bytes/fields or arbitrary exception text are retained. Install only
around the isolated operator client, before connect, and close after disconnect.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import threading
import time
import sys
from importlib import metadata

_COUNTERS = ('records_dropped', 'oversize', 'hook_errors', 'send_calls', 'send_requested',
             'send_returned', 'short_sends', 'send_exceptions', 'recv_calls', 'recv_bytes',
             'recv_eof', 'recv_timeouts', 'recv_exceptions', 'recvmsg_calls', 'recvmsg_bytes',
             'frames', 'partial_frames', 'queue_put', 'queue_get', 'decoder_entry',
             'decoder_return', 'decoder_exception', 'other_messages', 'sdk_logs_suppressed',
             'recv_full_chunks', 'recvmsg_empty', 'framing_buffer_max', 'queue_depth_max',
             'console_writes_suppressed', 'serialized_quotes_verified', 'unverified_quote_schema',
             'quote_socket_calls', 'quote_send_requested', 'quote_send_returned', 'quote_send_exceptions',
             'background_records_omitted', 'repeated_details_omitted')
_QUOTE = {1, 2, 4, 46, 57, 58}
_INT = re.compile(rb'-?[0-9]{1,10}\Z')
_SAFE = re.compile(r'[A-Za-z0-9 ._/-]{0,64}\Z')


def _integer(value):
    return int(value) if _INT.fullmatch(value) else None


def _message(body):
    # Only fixed, known schemas expose request IDs. Never retain values or text.
    fields = body.split(b'\0')
    if fields and fields[-1] == b'':
        fields.pop()
    msg = _integer(fields[0]) if fields else None
    if msg not in _QUOTE:
        return {'kind': 'OTHER'}
    out = {'kind': 'QUOTE', 'message_id': msg, 'field_count': len(fields)}
    if len(fields) > 2:
        out['request_id'] = _integer(fields[2])
    if msg in (1, 2, 46) and len(fields) > 3:
        out['tick_id'] = _integer(fields[3])
    return out


class TransportDiagnostic:
    """64 records x 4096 UTF-8 bytes, fixed saturating counters, no acquisition."""
    def __init__(self, client):
        self.client = client
        self.records = []
        self.counters = dict.fromkeys(_COUNTERS, 0)
        self.lock = threading.RLock()
        self.patches = []
        self.active = False
        self.restored = False
        self.installed = False
        self.hashes = {}
        self.started = time.monotonic()
        self.quote_window = False
        self.target_request = None
        self.background_records = 0
        self.aggregates = {}
        self.reader = None
        self.reader_stopped = True
        self.send_scope = threading.local()

    def count(self, name, amount=1):
        with self.lock:
            self.counters[name] = min(2**63-1, self.counters[name] + amount)

    def record(self, event, **facts):
        try:
            value = {'event': event, 'seconds': round(time.monotonic()-self.started, 6), **facts}
            encoded = json.dumps(value, ensure_ascii=True, allow_nan=False).encode()
            with self.lock:
                # Startup/global traffic has aggregate counters but at most eight
                # samples. The remaining 56 slots belong to the one target's
                # lifecycle, including completion/cleanup. Never evict evidence.
                target = (self.target_request is not None and
                          (facts.get('request_id') == self.target_request or
                           (self.quote_window and 'request_id' not in facts) or
                           event in ('quote_window_start', 'quote_window_end')))
                aggregate_events = {'socket_recv', 'recvmsg_return', 'frame_progress',
                                    'queue_put', 'queue_get', 'decoder_entry', 'decoder_return'}
                key = None
                if target and event in aggregate_events:
                    # Keep schema/dispatch failures separate from successful
                    # observations. Values/byte lengths are first samples only.
                    key = (event, facts.get('message_id'), facts.get('request_id'),
                           facts.get('kind'), facts.get('complete'),
                           facts.get('handler_kind'), facts.get('handler_known'),
                           facts.get('arity_ok'))
                    prior = self.aggregates.get(key)
                    if prior is not None:
                        prior['observations'] = min(2**63-1, prior['observations'] + 1)
                        self.count('repeated_details_omitted')
                        return
                    value['observations'] = 1
                    value['detail_policy'] = 'first_sample_only_all_occurrences_counted'
                    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False).encode()
                if len(encoded) > 4096:
                    self.count('oversize')
                    return
                if not target and self.background_records >= 8:
                    self.count('background_records_omitted')
                    return
                final_event = event in ('wrapper_completion', 'quote_window_end', 'wrapper_cleanup')
                if len(self.records) == 64 or (target and not final_event and len(self.records) >= 56):
                    self.count('records_dropped')
                    return
                self.records.append(value)
                if not target:
                    self.background_records += 1
                if key is not None:
                    self.aggregates[key] = value
        except BaseException:
            self.count('hook_errors')

    def observe(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except BaseException:
            self.count('hook_errors')
            return None

    def patch(self, obj, name, value):
        own = name in vars(obj)
        original = getattr(obj, name)
        self.patches.append((obj, name, own, original))
        setattr(obj, name, value)
        return original

    def _wire(self, frame):
        if len(frame) < 4 or int.from_bytes(frame[:4], 'big') != len(frame)-4:
            return
        fields = frame[4:].split(b'\0')
        if fields[-1:] == [b'']:
            fields.pop()
        if not fields or fields[0] not in (b'1', b'2', b'59'):
            return
        msg = _integer(fields[0])
        if msg != 1:
            self.record('outgoing_control', message_id=msg, bytes=len(frame))
            return {'message_id': msg}
        self.quote_window = True
        self.record('quote_window_start', counters=dict(self.counters))
        version = self.client.serverVersion()
        names = ['message_id', 'version', 'request_id']
        if version >= 47:
            names += ['con_id']
        names += ['symbol', 'sec_type', 'expiry', 'strike', 'right', 'multiplier',
                  'exchange', 'primary_exchange', 'currency', 'local_symbol']
        if version >= 68:
            names += ['trading_class']
        if version >= 40:
            names += ['delta_neutral_present']
        names += ['generic_ticks', 'snapshot']
        if version >= 114:
            names += ['regulatory_snapshot']
        if version >= 70:
            names += ['options']
        pairs = dict(zip(names, fields))
        valid = (len(fields) == len(names) and pairs.get('sec_type') == b'STK'
                 and pairs.get('delta_neutral_present', b'0') == b'0'
                 and pairs.get('generic_ticks') == b'' and pairs.get('options', b'') == b'')
        if not valid:
            self.count('unverified_quote_schema')
            self.record('serialized_quote', schema_verified=False, field_count=len(fields), bytes=len(frame))
            return
        from src.ibkr.evidence_safety import scrub_text
        safe = {}
        for name, raw in pairs.items():
            value = raw.decode('ascii', errors='strict')
            # Overlong/unsafe strings are omitted in full, never truncated.
            safe[name] = scrub_text(value) if _SAFE.fullmatch(value) else 'OMITTED_UNSAFE_OR_OVERLONG'
        self.count('serialized_quotes_verified')
        self.record('serialized_quote', schema_verified=True, server_version=version,
                    fields=safe, bytes=len(frame))
        return {'message_id': 1, 'request_id': _integer(pairs['request_id'])}

    def __enter__(self):
        from ibapi import client as sdk, connection, decoder, reader, comm, wrapper
        if self.active or self.client.isConnected():
            raise RuntimeError('Diagnostic requires unused disconnected client')
        self.active = True
        try:
            if metadata.version('ibapi') != '9.81.1.post1':
                raise RuntimeError('Unreviewed SDK distribution')
            for module in (sdk, connection, decoder, reader, comm, wrapper):
                with open(inspect.getsourcefile(module), 'rb') as source:
                    self.hashes[module.__name__] = hashlib.sha256(source.read()).hexdigest()
            self.record('sdk_identity', distribution=metadata.version('ibapi'),
                        python=sys.version.split()[0], hashes=self.hashes, signatures={
                            'reqMktData': str(inspect.signature(sdk.EClient.reqMktData)),
                            'sendMsg': str(inspect.signature(connection.Connection.sendMsg)),
                            'recvMsg': str(inspect.signature(connection.Connection.recvMsg)),
                            'read_msg': str(inspect.signature(comm.read_msg)),
                            'interpret': str(inspect.signature(decoder.Decoder.interpret)),
                            'interpretWithSignature': str(inspect.signature(decoder.Decoder.interpretWithSignature))})
            owner = self
            class QuietSDK(logging.Filter):
                def filter(self, record):
                    owner.count('sdk_logs_suppressed')
                    return False
            self.log_filter = QuietSDK()
            self.loggers = [logging.getLogger('ibapi.'+n) for n in
                            ('client', 'connection', 'decoder', 'reader', 'comm', 'wrapper')]
            for logger in self.loggers:
                logger.addFilter(self.log_filter)
            base_connection = sdk.Connection
            class ObservedConnection(base_connection):
                def connect(conn):
                    result = super().connect()
                    if conn.socket is not None:
                        conn.socket = _Socket(conn.socket, owner)
                    return result
                def sendMsg(conn, message):
                    previous = getattr(owner.send_scope, 'facts', None)
                    facts = owner.observe(owner._wire, message) or {}
                    owner.send_scope.facts = facts
                    try:
                        result = super().sendMsg(message)
                    except BaseException as exc:
                        owner.record('connection_send_exception', exception_class=type(exc).__name__, **facts)
                        raise
                    else:
                        owner.record('connection_send_return', requested=len(message), returned=result, **facts)
                        return result
                    finally:
                        owner.send_scope.facts = previous
                def recvMsg(conn):
                    owner.count('recvmsg_calls')
                    result = super().recvMsg()
                    owner.count('recvmsg_bytes', len(result))
                    if not result:
                        owner.count('recvmsg_empty')
                    if owner.quote_window:
                        owner.record('recvmsg_return', returned=len(result))
                    return result
            self.patch(sdk, 'Connection', ObservedConnection)
            base_reader = sdk.reader.EReader
            class ObservedReader(base_reader):
                def __init__(reader, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    owner.reader = reader
            self.patch(sdk.reader, 'EReader', ObservedReader)
            base_decoder = sdk.decoder.Decoder
            class ObservedDecoder(base_decoder):
                def interpret(dec, fields):
                    owner.count('decoder_entry')
                    fact = owner.observe(_message, b'\0'.join(fields)) or {'kind': 'OTHER'}
                    if fact['kind'] != 'OTHER':
                        def handler_facts():
                            handle = dec.msgId2handleInfo.get(fact['message_id'])
                            extra = {'handler_known': handle is not None,
                                     'handler_kind': ('SIGNATURE' if handle and handle.wrapperMeth else
                                                      'CUSTOM' if handle and handle.processMeth else 'NONE')}
                            if handle and handle.wrapperMeth:
                                extra['arity_ok'] = (handle.wrapperParams is not None and
                                    len(fields)-2 == len(handle.wrapperParams)-1)
                            return extra
                        fact.update(owner.observe(handler_facts) or {})
                        owner.record('decoder_entry', **fact)
                    else:
                        owner.count('other_messages')
                    try:
                        result = super().interpret(fields)
                    except BaseException as exc:
                        owner.count('decoder_exception')
                        if fact['kind'] != 'OTHER':
                            owner.record('decoder_exception', exception_class=type(exc).__name__, **fact)
                        raise
                    owner.count('decoder_return')
                    if fact['kind'] != 'OTHER':
                        owner.record('decoder_return', **fact)
                    return result
            self.patch(sdk.decoder, 'Decoder', ObservedDecoder)
            original_read = comm.read_msg
            def read_msg(buf):
                result = original_read(buf)
                size, body, remaining = result
                owner.count('frames' if body else 'partial_frames')
                with owner.lock:
                    owner.counters['framing_buffer_max'] = max(owner.counters['framing_buffer_max'], len(remaining))
                fact = owner.observe(_message, body) if body else None
                if owner.quote_window:
                    owner.record('frame_progress', buffered=len(buf), complete=bool(body),
                                 remaining=len(remaining), **(fact or {}))
                return result
            self.patch(comm, 'read_msg', read_msg)
            queue = self.client.msg_queue
            original_put, original_get = queue.put, queue.get
            def put(item, *args, **kwargs):
                result = original_put(item, *args, **kwargs)
                owner.count('queue_put')
                with owner.lock:
                    owner.counters['queue_depth_max'] = max(owner.counters['queue_depth_max'], queue.qsize())
                fact = owner.observe(_message, item)
                if fact and fact['kind'] != 'OTHER':
                    owner.record('queue_put', **fact)
                return result
            def get(*args, **kwargs):
                item = original_get(*args, **kwargs)
                owner.count('queue_get')
                fact = owner.observe(_message, item)
                if fact and fact['kind'] != 'OTHER':
                    owner.record('queue_get', **fact)
                return item
            self.patch(queue, 'put', put)
            self.patch(queue, 'get', get)
            # Existing wrapper counters retain authority. Suppress their unbounded
            # console detail; retain correlation inside this diagnostic's one cap.
            trace = self.client._quote_trace
            def emit(event, req_id, facts):
                # Trace fields are already privacy bounded; retain only safe facts.
                allowed = ('kind', 'reason', 'outcome', 'requested_type',
                           'returned_type', 'snapshot', 'regulatory_snapshot', 'owner', 'tick_type',
                           'cancel_outcome', 'active_after', 'ticker_present_after', 'event_present_after')
                if event == 'request' and owner.target_request is None:
                    owner.target_request = req_id
                elif event == 'request' and req_id != owner.target_request:
                    owner.count('hook_errors')  # This capture supports one target only.
                owner.record('wrapper_'+event, request_id=req_id, **{k: v for k, v in facts.items() if k in allowed})
                if event == 'completion':
                    owner.record('quote_window_end', counters=dict(owner.counters))
                    owner.quote_window = False
            self.patch(trace, '_emit', emit)
            self.installed = True
            self.record('hooks_installed')
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        # Retain the reader reference before SDK reset discards it. Caller must
        # disconnect first; bounded join never waits on the current thread.
        reader = self.reader
        if reader and reader.ident is not None and reader is not threading.current_thread():
            reader.join(timeout=2)
            self.reader_stopped = not reader.is_alive()
            if not self.reader_stopped:
                self.count('hook_errors')
        if self.installed and self.client.isConnected():
            self.count('hook_errors')
        while self.patches:
            obj, name, own, original = self.patches.pop()
            if own:
                setattr(obj, name, original)
            else:
                delattr(obj, name)
        for logger in getattr(self, 'loggers', []):
            logger.removeFilter(self.log_filter)
        # SDK drops its socket on disconnect. A still-connected proxy is restored
        # by identity too, so no diagnostic object survives scope cleanup.
        conn = getattr(self.client, 'conn', None)
        if conn and isinstance(conn.socket, _Socket):
            conn.socket = conn.socket.original
        self.active = False
        self.restored = True

    def __exit__(self, *exc):
        self.close()

    def snapshot(self):
        with self.lock:
            coverage = bool(self.installed and self.hashes and self.restored and self.reader_stopped
                            and not any(self.counters[k] for k in
                                ('records_dropped', 'oversize', 'hook_errors', 'unverified_quote_schema')))
            return {'records': [dict(row) for row in self.records], 'counters': dict(self.counters),
                    'coverage_scope': 'single_target_lifecycle_with_aggregate_stages',
                    'detail_policy': 'background_max_8_samples_target_stages_first_sample_and_counts',
                    'target_request_id': self.target_request,
                    'source_hashes': dict(self.hashes), 'reader_stopped': self.reader_stopped,
                    'hooks_restored': self.restored, 'hooks_installed_completely': self.installed,
                    'coverage_verified': coverage,
                    'absence_claims_valid': (coverage and self.counters['serialized_quotes_verified'] == 1
                                            and self.counters['quote_socket_calls'] == 1)}


class _Socket:
    def __init__(self, original, owner):
        self.original, self.owner = original, owner

    def __getattr__(self, name):
        return getattr(self.original, name)

    def send(self, data, *args, **kwargs):
        owner = self.owner
        owner.count('send_calls'); owner.count('send_requested', len(data))
        facts = getattr(owner.send_scope, 'facts', None) or {}
        is_quote = facts.get('message_id') == 1
        if is_quote:
            owner.count('quote_socket_calls'); owner.count('quote_send_requested', len(data))
        try:
            result = self.original.send(data, *args, **kwargs)
        except BaseException as exc:
            owner.count('send_exceptions')
            if is_quote:
                owner.count('quote_send_exceptions')
            owner.record('socket_send_exception', requested=len(data), exception_class=type(exc).__name__, **facts)
            raise
        owner.count('send_returned', result)
        if is_quote:
            owner.count('quote_send_returned', result)
        if result < len(data):
            owner.count('short_sends')
        owner.record('socket_send', requested=len(data), returned=result, **facts)
        return result

    def recv(self, size, *args, **kwargs):
        import socket
        owner = self.owner
        owner.count('recv_calls')
        try:
            result = self.original.recv(size, *args, **kwargs)
        except BaseException as exc:
            owner.count('recv_timeouts' if isinstance(exc, socket.timeout) else 'recv_exceptions')
            # Fixed counters for frequent socket timeouts, detail only exceptions.
            if not isinstance(exc, socket.timeout) or owner.counters['recv_timeouts'] == 1:
                owner.record('socket_recv_exception', exception_class=type(exc).__name__)
            raise
        owner.count('recv_bytes', len(result))
        if len(result) == size:
            owner.count('recv_full_chunks')
        if not result:
            owner.count('recv_eof')
        if owner.quote_window:
            owner.record('socket_recv', requested=size, returned=len(result))
        return result
