"""Opt-in, dedicated-process SDK observation. Never changes SDK wire operations.

No raw inbound bytes/fields or arbitrary exception text are retained. Install only
around the isolated operator client, before connect, and close after disconnect.
"""
from __future__ import annotations

import builtins
import copy
import hashlib
import inspect
import json
import logging
import re
import queue as queue_module
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


def _message(body, profile='quotes'):
    # Only fixed, known schemas expose request IDs. Never retain values or text.
    fields = body.split(b'\0')
    if fields and fields[-1] == b'':
        fields.pop()
    msg = _integer(fields[0]) if fields else None
    if profile == 'final-orders':
        kind = {3: 'ORDER_STATUS', 4: 'ERROR', 5: 'ORDER', 53: 'ORDER_END'}.get(msg, 'OTHER')
        # Payloads/identifiers never leave the parser. End has a fixed schema;
        # custom order schemas are validated by the actual pinned SDK decoder.
        return {'kind': kind, 'field_count': len(fields),
                **({'message_id': msg} if kind != 'OTHER' else {}),
                'schema_known': (msg == 53 and fields == [b'53', b'1']) or msg in (3, 4, 5)}
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
    def __init__(self, client, *, profile='quotes'):
        if profile not in ('quotes', 'final-orders'):
            raise ValueError('Unknown transport profile')
        self.profile = profile
        self.client = client
        self.order_window = False
        self.pending_frame_bytes = 0
        self.loop_stopped = True
        self.observation_failed = False
        self.records = []
        self.counters = dict.fromkeys(_COUNTERS, 0)
        if profile == 'final-orders':
            self.counters.update(dict.fromkeys(('order_query_calls', 'order_query_returns',
                'order_query_exceptions', 'order_serialized', 'order_schema_unknown',
                'order_socket_calls', 'order_send_requested', 'order_send_returned',
                'order_send_exceptions', 'order_full_send', 'order_callback_entry', 'order_callback_return',
                'end_callback_entry', 'end_callback_return', 'error_callback_entry',
                'error_callback_return', 'reader_start', 'reader_exit', 'loop_start',
                'loop_exit', 'reader_logged_exception', 'reader_abnormal_exit', 'queue_exceptions', 'unknown_messages') + tuple(
                    stage+'_'+kind for stage in ('frame','put','get','decode','decoded')
                    for kind in ('ORDER','ORDER_END','ORDER_STATUS','ERROR')), 0))
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

    def _safe(self, method, *args, **kwargs):
        # Diagnostic failures cannot suppress or replace a transport operation.
        if self.profile != 'final-orders':
            return getattr(self, method)(*args, **kwargs)
        try:
            return getattr(self, method)(*args, **kwargs)
        except BaseException:
            self.observation_failed = True
            self.counters['hook_errors'] = min(2**63-1, self.counters.get('hook_errors', 0)+1)
            return None

    def count(self, name, amount=1):
        with self.lock:
            self.counters[name] = min(2**63-1, self.counters[name] + amount)

    def record(self, event, **facts):
        try:
            if self.profile == 'final-orders':
                events = {'sdk_identity', 'hooks_installed', 'serialized_order_query',
                    'reader_exception', 'connection_send_exception', 'connection_send_return',
                    'recvmsg_return', 'reader_start', 'reader_exit', 'decoder_entry', 'decoder_return',
                    'decoder_exception', 'frame_progress', 'queue_put', 'queue_get', 'order_query_begin',
                    'order_query_exception', 'order_query_end', 'order_callback', 'end_callback',
                    'error_callback', 'callback_exception', 'loop_start', 'loop_exit', 'order_cleanup',
                    'socket_send_exception', 'socket_send', 'socket_recv_exception', 'socket_recv', 'queue_exception'}
                if event not in events:
                    self.count('hook_errors')
                    event = 'unrecognized_observation'
                    facts = {}
                numeric = {'requested', 'returned', 'bytes', 'field_count', 'message_id',
                           'buffered', 'remaining', 'server_version', 'error_code'}
                flags = {'complete', 'handler_known', 'arity_ok', 'schema_known', 'alive'}
                enums = {'kind': {'ORDER', 'ORDER_END', 'ORDER_STATUS', 'ERROR', 'OTHER'},
                         'handler_kind': {'SIGNATURE', 'CUSTOM', 'NONE'}}
                safe = {k: v for k, v in facts.items() if
                        (k in numeric and type(v) is int and abs(v) <= 2**63-1) or
                        (k in flags and type(v) is bool) or
                        (k in enums and v in enums[k])}
                if event == 'sdk_identity':
                    safe['hashes'] = dict(self.hashes)
                if 'counters' in facts:
                    safe['counters'] = dict(self.counters)
                if 'exception_class' in facts:
                    raw = facts['exception_class']
                    safe['exception_class'] = raw if type(raw) is str and isinstance(getattr(builtins, raw, None), type) and issubclass(getattr(builtins, raw), BaseException) else 'OTHER_EXCEPTION'
                facts = safe
            value = {'event': event, 'seconds': round(time.monotonic()-self.started, 6), **facts}
            encoded = json.dumps(value, ensure_ascii=True, allow_nan=False).encode()
            with self.lock:
                if len(encoded) > 4096:
                    self.count('oversize')
                    return
                # Startup/global traffic has aggregate counters but at most eight
                # samples. The remaining 56 slots belong to the one target's
                # lifecycle, including completion/cleanup. Never evict evidence.
                target = self.order_window if self.profile == 'final-orders' else (self.target_request is not None and
                          (facts.get('request_id') == self.target_request or
                           (self.quote_window and 'request_id' not in facts) or
                           event in ('quote_window_start', 'quote_window_end')))
                aggregate_events = {'socket_recv', 'recvmsg_return', 'frame_progress',
                                    'queue_put', 'queue_get', 'decoder_entry', 'decoder_return'}
                if self.profile == 'final-orders':
                    aggregate_events |= {'order_callback', 'error_callback', 'end_callback'}
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
                if not target and (self.background_records >= 8 or len(self.records) >= 56):
                    self.count('background_records_omitted')
                    return
                final_event = event in ('wrapper_completion', 'quote_window_end', 'wrapper_cleanup', 'order_query_end', 'order_cleanup', 'end_callback', 'reader_exit', 'loop_exit')
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

    def _facts(self, body):
        facts = _message(body, self.profile)
        if self.profile == 'final-orders' and self.order_window:
            if facts['kind'] == 'OTHER':
                self.count('unknown_messages')
            elif not facts['schema_known']:
                self.count('order_schema_unknown')
        return facts

    @staticmethod
    def _has_unconsumed_fields(fields):
        sentinel = object()
        return next(fields, sentinel) is not sentinel

    def _queue_depth(self, queue):
        with self.lock:
            self.counters['queue_depth_max'] = max(self.counters['queue_depth_max'], queue.qsize())

    def _reader_exit_state(self, reader):
        connected = reader.conn.isConnected()
        if connected and not self.client._stop_event.is_set():
            self.count('reader_abnormal_exit')
        self.record('reader_exit', alive=connected)

    def _order_stage(self, stage, facts):
        if self.profile == 'final-orders' and self.order_window and facts.get('kind') != 'OTHER':
            self.count(stage+'_'+facts['kind'])

    def _wire(self, frame):
        if len(frame) < 4 or int.from_bytes(frame[:4], 'big') != len(frame)-4:
            return
        fields = frame[4:].split(b'\0')
        if fields[-1:] == [b'']:
            fields.pop()
        if self.profile == 'final-orders':
            if fields == [b'16', b'1'] and self.order_window:
                self.count('order_serialized')
                self.record('serialized_order_query', message_id=16, field_count=2, bytes=len(frame),
                            server_version=self.client.serverVersion())
                return {'message_id': 16}
            # Handshake/startApi/type controls are counted, not exported.
            if self.order_window:
                self.count('order_schema_unknown')
            return
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
                    owner._safe('count', 'sdk_logs_suppressed')
                    if owner.profile == 'final-orders' and record.name in ('ibapi.reader', 'ibapi.decoder') and (record.exc_info or record.levelno >= logging.ERROR):
                        owner._safe('count', 'reader_logged_exception')
                        owner._safe('record', 'reader_exception', exception_class=record.exc_info[0].__name__ if record.exc_info else 'OTHER_EXCEPTION')
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
                    facts = owner._safe('observe', owner._wire, message) or {}
                    owner.send_scope.facts = facts
                    try:
                        result = super().sendMsg(message)
                    except BaseException as exc:
                        owner._safe('record', 'connection_send_exception', exception_class=type(exc).__name__, **facts)
                        raise
                    else:
                        owner._safe('record', 'connection_send_return', requested=len(message), returned=result, **facts)
                        return result
                    finally:
                        owner.send_scope.facts = previous
                def recvMsg(conn):
                    owner._safe('count', 'recvmsg_calls')
                    result = super().recvMsg()
                    owner._safe('count', 'recvmsg_bytes', len(result))
                    if not result:
                        owner._safe('count', 'recvmsg_empty')
                    if owner.quote_window or owner.order_window:
                        owner._safe('record', 'recvmsg_return', returned=len(result))
                    return result
            self.patch(sdk, 'Connection', ObservedConnection)
            base_reader = sdk.reader.EReader
            class ObservedReader(base_reader):
                def __init__(reader, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    owner.reader = reader
                def run(reader):
                    if owner.profile != 'final-orders':
                        return super().run()
                    owner._safe('count', 'reader_start'); owner._safe('record', 'reader_start')
                    try:
                        return super().run()
                    finally:
                        owner._safe('count', 'reader_exit'); owner._safe('_reader_exit_state', reader)
            self.patch(sdk.reader, 'EReader', ObservedReader)
            base_decoder = sdk.decoder.Decoder
            class ObservedDecoder(base_decoder):
                def __init__(dec, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    if owner.profile == 'final-orders':
                        # Per-instance handles only. Invoke the pinned custom parser
                        # once, then inspect its otherwise discarded iterator tail.
                        dec.msgId2handleInfo = dict(dec.msgId2handleInfo)
                        for msg_id in (3, 5):
                            original = dec.msgId2handleInfo.get(msg_id)
                            if original is None or original.processMeth is None:
                                owner._safe('count', 'order_schema_unknown')
                                continue
                            handle = copy.copy(original)
                            def checked(decoder, fields, _original=original.processMeth):
                                result = _original(decoder, fields)
                                if owner._safe('_has_unconsumed_fields', fields):
                                    owner._safe('count', 'order_schema_unknown')
                                return result
                            handle.processMeth = checked
                            dec.msgId2handleInfo[msg_id] = handle
                def interpret(dec, fields):
                    owner._safe('count', 'decoder_entry')
                    fact = owner._safe('observe', owner._facts, b'\0'.join(fields)) or {'kind': 'OTHER'}
                    owner._safe('_order_stage', 'decode', fact)
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
                        fact.update(owner._safe('observe', handler_facts) or {})
                        if owner.profile == 'final-orders' and (not fact.get('handler_known') or fact.get('handler_kind') == 'NONE' or fact.get('arity_ok') is False):
                            owner._safe('count', 'order_schema_unknown')
                        owner._safe('record', 'decoder_entry', **fact)
                    else:
                        owner._safe('count', 'other_messages')
                    try:
                        result = super().interpret(fields)
                    except BaseException as exc:
                        owner._safe('count', 'decoder_exception')
                        if fact['kind'] != 'OTHER':
                            owner._safe('record', 'decoder_exception', exception_class=type(exc).__name__, **fact)
                        raise
                    owner._safe('count', 'decoder_return')
                    owner._safe('_order_stage', 'decoded', fact)
                    if fact['kind'] != 'OTHER':
                        owner._safe('record', 'decoder_return', **fact)
                    return result
            self.patch(sdk.decoder, 'Decoder', ObservedDecoder)
            original_read = comm.read_msg
            def read_msg(buf):
                result = original_read(buf)
                size, body, remaining = result
                if owner.profile == 'final-orders':
                    owner.pending_frame_bytes = len(remaining) if body else len(buf)
                owner._safe('count', 'frames' if body else 'partial_frames')
                with owner.lock:
                    owner.counters['framing_buffer_max'] = max(owner.counters['framing_buffer_max'], len(remaining))
                fact = owner._safe('observe', owner._facts, body) if body else None
                if fact:
                    owner._safe('_order_stage', 'frame', fact)
                if owner.quote_window or owner.order_window:
                    owner._safe('record', 'frame_progress', buffered=len(buf), complete=bool(body),
                                 remaining=len(remaining), **(fact or {}))
                return result
            self.patch(comm, 'read_msg', read_msg)
            queue = self.client.msg_queue
            original_put, original_get = queue.put, queue.get
            def put(item, *args, **kwargs):
                try:
                    result = original_put(item, *args, **kwargs)
                except BaseException as exc:
                    if owner.profile == 'final-orders':
                        owner._safe('count', 'queue_exceptions')
                        owner._safe('record', 'queue_exception', exception_class=type(exc).__name__)
                    raise
                owner._safe('count', 'queue_put')
                owner._safe('_queue_depth', queue)
                fact = owner._safe('observe', owner._facts, item)
                if fact:
                    owner._safe('_order_stage', 'put', fact)
                if fact and fact['kind'] != 'OTHER':
                    owner._safe('record', 'queue_put', **fact)
                return result
            def get(*args, **kwargs):
                try:
                    item = original_get(*args, **kwargs)
                except queue_module.Empty:
                    raise  # Ordinary SDK polling; not lost evidence.
                except BaseException as exc:
                    if owner.profile == 'final-orders':
                        owner._safe('count', 'queue_exceptions')
                        owner._safe('record', 'queue_exception', exception_class=type(exc).__name__)
                    raise
                owner._safe('count', 'queue_get')
                fact = owner._safe('observe', owner._facts, item)
                if fact:
                    owner._safe('_order_stage', 'get', fact)
                if fact and fact['kind'] != 'OTHER':
                    owner._safe('record', 'queue_get', **fact)
                return item
            self.patch(queue, 'put', put)
            self.patch(queue, 'get', get)
            # Existing wrapper counters retain authority. Suppress their unbounded
            # console detail; retain correlation inside this diagnostic's one cap.
            if self.profile == 'final-orders':
                self._install_order_wrappers()
                self.installed = True
                self.record('hooks_installed')
                return self
            trace = self.client._quote_trace
            def emit(event, req_id, facts):
                # Trace fields are already privacy bounded; retain only safe facts.
                allowed = ('kind', 'reason', 'outcome', 'requested_type',
                           'returned_type', 'snapshot', 'regulatory_snapshot', 'owner', 'tick_type',
                           'cancel_outcome', 'active_after', 'ticker_present_after', 'event_present_after')
                if event == 'request' and owner.target_request is None:
                    owner.target_request = req_id
                elif event == 'request' and req_id != owner.target_request:
                    owner._safe('count', 'hook_errors')  # This capture supports one target only.
                owner._safe('record', 'wrapper_'+event, request_id=req_id, **{k: v for k, v in facts.items() if k in allowed})
                if event == 'completion':
                    owner._safe('record', 'quote_window_end', counters=dict(owner.counters))
                    owner.quote_window = False
            self.patch(trace, '_emit', emit)
            self.installed = True
            self.record('hooks_installed')
            return self
        except BaseException:
            self.close()
            raise

    def _install_order_wrappers(self):
        owner = self
        original_query = self.client.reqAllOpenOrders
        def query():
            owner.order_window = True
            owner._safe('count', 'order_query_calls')
            owner._safe('record', 'order_query_begin', counters=dict(owner.counters))
            try:
                result = original_query()
            except BaseException as exc:
                owner._safe('count', 'order_query_exceptions')
                owner._safe('record', 'order_query_exception', exception_class=type(exc).__name__)
                raise
            else:
                owner._safe('count', 'order_query_returns')
                return result
            finally:
                owner._safe('record', 'order_query_end')
        self.patch(self.client, 'reqAllOpenOrders', query)
        for method, prefix in (('openOrder', 'order'), ('openOrderEnd', 'end'), ('error', 'error')):
            original = getattr(self.client, method)
            def callback(*args, _original=original, _prefix=prefix, **kwargs):
                if owner.order_window:
                    owner._safe('count', _prefix+'_callback_entry')
                owner._safe('record', _prefix+'_callback', **({'error_code': args[1]} if _prefix == 'error' and len(args)>1 else {}))
                try:
                    value = _original(*args, **kwargs)
                except BaseException as exc:
                    owner._safe('count', 'hook_errors')  # Failure precludes dispatch/absence proof.
                    owner._safe('record', 'callback_exception', exception_class=type(exc).__name__)
                    raise
                if owner.order_window:
                    owner._safe('count', _prefix+'_callback_return')
                return value
            self.patch(self.client, method, callback)
        original_loop = self.client._run_loop
        def loop():
            owner.loop_stopped = False
            owner._safe('count', 'loop_start'); owner._safe('record', 'loop_start')
            try:
                return original_loop()
            finally:
                owner.loop_stopped = True
                owner._safe('count', 'loop_exit'); owner._safe('record', 'loop_exit')
        self.patch(self.client, '_run_loop', loop)

    def close(self):
        if self.profile == 'final-orders' and self.restored:
            return
        # Retain the reader reference before SDK reset discards it. Caller must
        # disconnect first; bounded join never waits on the current thread.
        reader = self.reader
        cleanup_failed = False
        if self.profile == 'final-orders':
            self.reader_stopped = reader is None
        try:
            if reader and reader.ident is not None and reader is not threading.current_thread():
                reader.join(timeout=2)
                self.reader_stopped = not reader.is_alive()
                if not self.reader_stopped:
                    self._safe('count', 'hook_errors')
            if self.installed and self.client.isConnected():
                self._safe('count', 'hook_errors')
        except BaseException:
            if self.profile != 'final-orders':
                raise
            cleanup_failed = self.observation_failed = True
            self._safe('count', 'hook_errors')
        failed = []
        while self.patches:
            obj, name, own, original = self.patches.pop()
            try:
                if own:
                    setattr(obj, name, original)
                else:
                    delattr(obj, name)
            except BaseException:
                if self.profile != 'final-orders':
                    raise
                self.observation_failed = True
                self._safe('count', 'hook_errors')
                failed.append((obj, name, own, original))
        self.patches.extend(failed)
        for logger in getattr(self, 'loggers', []):
            try:
                logger.removeFilter(self.log_filter)
            except BaseException:
                if self.profile != 'final-orders':
                    raise
                cleanup_failed = self.observation_failed = True
                self._safe('count', 'hook_errors')
        # SDK drops its socket on disconnect. A still-connected proxy is restored
        # by identity too, so no diagnostic object survives scope cleanup.
        conn = getattr(self.client, 'conn', None)
        try:
            if conn and isinstance(conn.socket, _Socket):
                conn.socket = conn.socket.original
        except BaseException:
            if self.profile != 'final-orders':
                raise
            cleanup_failed = self.observation_failed = True
            self._safe('count', 'hook_errors')
        if self.profile == 'final-orders':
            thread = getattr(self.client, '_thread', None)
            try:
                self.loop_stopped = not bool(thread and thread.is_alive())
            except BaseException:
                self.loop_stopped = False
                cleanup_failed = self.observation_failed = True
            self._safe('record', 'order_cleanup', alive=not self.loop_stopped, counters=dict(self.counters))
        self.active = False
        self.restored = not bool(self.patches) and not cleanup_failed

    def __exit__(self, *exc):
        self.close()

    def snapshot(self):
        with self.lock:
            coverage = bool(self.installed and self.hashes and self.restored and self.reader_stopped
                            and not any(self.counters[k] for k in
                                ('records_dropped', 'oversize', 'hook_errors', 'unverified_quote_schema')))
            if self.profile == 'final-orders':
                coverage = bool(coverage and self.loop_stopped and not self.observation_failed
                    and not self.pending_frame_bytes
                    and self.counters['reader_start'] == self.counters['reader_exit'] == 1
                    and self.counters['loop_start'] == self.counters['loop_exit'] == 1
                    and not any(self.counters[k] for k in
                    ('order_schema_unknown', 'reader_logged_exception', 'unknown_messages', 'decoder_exception', 'reader_abnormal_exit', 'queue_exceptions', 'recv_exceptions')))
                sent = (self.counters['order_query_calls'] == self.counters['order_serialized'] ==
                        self.counters['order_socket_calls'] == 1 and self.counters['order_send_requested'] > 0
                        and self.counters['order_send_requested'] == self.counters['order_send_returned']
                        and not self.counters['order_send_exceptions'] and not self.counters['short_sends'])
                stages = [('query_method', 'order_query_calls'), ('serialized', 'order_serialized'),
                          ('local_socket_accepted', 'order_full_send'), ('end_frame', 'frame_ORDER_END'),
                          ('end_queued', 'put_ORDER_END'), ('end_dequeued', 'get_ORDER_END'),
                          ('end_decoder', 'decode_ORDER_END'), ('end_callback', 'end_callback_return')]
                end_stage = next((name for name, key in reversed(stages) if self.counters[key]), 'none')
                order_stages = [('order_frame', 'frame_ORDER'), ('order_queued', 'put_ORDER'),
                                ('order_dequeued', 'get_ORDER'), ('order_decoder', 'decode_ORDER'),
                                ('order_callback', 'order_callback_return')]
                order_stage = next((name for name, key in reversed(order_stages) if self.counters[key]), None)
                return {'profile': self.profile, 'records': [dict(row) for row in self.records],
                        'counters': dict(self.counters), 'source_hashes': dict(self.hashes),
                        'coverage_scope': 'one_fresh_client_one_order_query', 'coverage_verified': coverage,
                        'absence_claims_valid': coverage and sent,
                        'last_positive_stage': end_stage if self.counters['frame_ORDER_END'] else (order_stage or end_stage),
                        'end_last_positive_stage': end_stage,
                        'unknowns': ['broker_receipt_and_processing_not_proven_by_local_send'] + [name+'_not_observed' for name, key in stages if not self.counters[key]],
                        'hooks_restored': self.restored, 'reader_stopped': self.reader_stopped,
                        'callback_loop_stopped': self.loop_stopped}
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
        owner._safe('count', 'send_calls'); owner._safe('count', 'send_requested', len(data))
        facts = getattr(owner.send_scope, 'facts', None) or {}
        is_quote = facts.get('message_id') == 1
        is_order = owner.profile == 'final-orders' and facts.get('message_id') == 16
        if is_order:
            owner._safe('count', 'order_socket_calls'); owner._safe('count', 'order_send_requested', len(data))
        if is_quote:
            owner._safe('count', 'quote_socket_calls'); owner._safe('count', 'quote_send_requested', len(data))
        try:
            result = self.original.send(data, *args, **kwargs)
        except BaseException as exc:
            owner._safe('count', 'send_exceptions')
            if is_order:
                owner._safe('count', 'order_send_exceptions')
            if is_quote:
                owner._safe('count', 'quote_send_exceptions')
            owner._safe('record', 'socket_send_exception', requested=len(data), exception_class=type(exc).__name__, **facts)
            raise
        owner._safe('count', 'send_returned', result)
        if is_order:
            owner._safe('count', 'order_send_returned', result)
            if result == len(data):
                owner._safe('count', 'order_full_send')
        if is_quote:
            owner._safe('count', 'quote_send_returned', result)
        if result < len(data):
            owner._safe('count', 'short_sends')
        owner._safe('record', 'socket_send', requested=len(data), returned=result, **facts)
        return result

    def recv(self, size, *args, **kwargs):
        import socket
        owner = self.owner
        owner._safe('count', 'recv_calls')
        try:
            result = self.original.recv(size, *args, **kwargs)
        except BaseException as exc:
            owner._safe('count', 'recv_timeouts' if isinstance(exc, socket.timeout) else 'recv_exceptions')
            # Fixed counters for frequent socket timeouts, detail only exceptions.
            if not isinstance(exc, socket.timeout) or owner.counters['recv_timeouts'] == 1:
                owner._safe('record', 'socket_recv_exception', exception_class=type(exc).__name__)
            raise
        owner._safe('count', 'recv_bytes', len(result))
        if len(result) == size:
            owner._safe('count', 'recv_full_chunks')
        if not result:
            owner._safe('count', 'recv_eof')
        if owner.quote_window or owner.order_window:
            owner._safe('record', 'socket_recv', requested=size, returned=len(result))
        return result
