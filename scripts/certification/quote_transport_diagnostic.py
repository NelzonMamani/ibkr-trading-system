"""Prepared operator-only quote diagnostic. Importing does not acquire data."""
import ast
import contextlib
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def manifest(repo):
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo, timeout=10).decode().split('\0')
    return {name: digest(repo/name) for name in names if name}


def acquire(client, put):
    from ibapi.scanner import ScannerSubscription
    from src.core.acquisition import acquisition_deadline, checkpoint, wait_event
    from src.ibkr.market_data_client import _clean, _returned_market_data_type, _resolve_snapshot_timestamp
    from src.config.config_resolver import get_config
    subscription = ScannerSubscription()
    subscription.instrument, subscription.locationCode, subscription.scanCode = 'STK', 'STK.US.MAJOR', 'TOP_PERC_GAIN'
    subscription.numberOfRows, subscription.abovePrice, subscription.belowPrice = 50, 1, 20
    result = {'scan_outcome': 'UNAVAILABLE', 'selected': [], 'quotes': [], 'PAPER_READY': False}
    with acquisition_deadline(time.monotonic() + 25):
        try:
            rows = client.reqScannerData(subscription)  # Exactly ONE; never robust_scan.
        finally:
            scan_receipt = dict(client.last_scanner_request)
            error = scan_receipt.pop('error', None)
            scan_receipt['error_present'] = error is not None
            scan_receipt['error_code'] = (error[0] if isinstance(error, tuple) and
                                          error and type(error[0]) is int else None)
            put('scanner.json', scan_receipt)
        receipt = client.last_scanner_request
        if not (receipt.get('completion_status') == 'COMPLETE' and receipt.get('end_received')
                and receipt.get('wait_signalled') and receipt.get('error') is None
                and receipt.get('connected') and client.is_connected()
                and receipt.get('row_count') == len(rows)):
            raise RuntimeError('Scanner completion/ownership proof unavailable')
        result['scan_outcome'] = 'CONFIRMED_EMPTY' if not rows else 'COMPLETE_NONEMPTY'
        put('acquisition.json', result)
        if not rows:
            return result  # No quote, retry, substitute or fallback.
        selected, seen = [], set()
        for row in sorted(rows, key=lambda r: r.rank):
            c = row.contractDetails.contract
            if (c.secType != 'STK' or c.currency != 'USD' or type(c.conId) is not int
                    or c.conId <= 0 or not c.symbol or len(c.symbol) > 64 or c.conId in seen):
                continue
            seen.add(c.conId)
            c = copy.copy(c)
            c.exchange = 'SMART'  # Normal routing instruction, not issuer identity.
            selected.append(c)
            result['selected'].append({'rank': row.rank, 'symbol': c.symbol, 'con_id': c.conId,
                                       'primary_exchange': c.primaryExchange, 'route': c.exchange})
            if len(selected) == 1:
                break
        put('acquisition.json', result)
        for c in selected:
            checkpoint()
            ticker = client.reqMktData(c, genericTickList='', snapshot=True, regulatorySnapshot=False)
            req = ticker.reqId
            reason = 'interrupted'
            try:
                signalled = wait_event(client._market_events[req], 5)
                with client._lock:
                    client._raise_if_request_id_conflicted(req)
                    t = copy.deepcopy(vars(ticker))
                    # Compare the retained observation with a clock sampled after
                    # its copy, never with a pre-lock clock from an older state.
                    now = datetime.now(timezone.utc)
                from types import SimpleNamespace
                t = SimpleNamespace(**t)
                reason = 'snapshot_end' if t.snapshotEnd else 'broker_error' if t.brokerErrors else 'timeout'
                fields = {k: _clean(getattr(t, k, None)) for k in ('bid', 'ask', 'last', 'close', 'volume')}
                for k, value in fields.items():
                    if value is not None and (value < 0 if k == 'volume' else value <= 0):
                        fields[k] = None
                stamp = _resolve_snapshot_timestamp(t)
                age = (now-stamp).total_seconds() if stamp else None
                returned = _returned_market_data_type(t)
                available = bool(signalled and t.snapshotEnd and not t.brokerErrors
                    and client.is_connected() and returned != 'UNKNOWN'
                    and age is not None and 0 <= age <= int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS'))
                    and all(v is not None for v in fields.values()))
                result['quotes'].append({'symbol': c.symbol, 'con_id': c.conId, 'request_id': req,
                    'requested_type': 'DELAYED', 'returned_type': returned, 'snapshot_complete': t.snapshotEnd,
                    'market_timestamp_utc': stamp.isoformat() if stamp else None, 'age_seconds': age,
                    'field_presence': {k: v is not None for k, v in fields.items()}, 'diagnostic_fields_available': available,
                    'canonical_qualification': 'NOT_PERFORMED',
                    'completion_reason': reason})
            finally:
                client.record_quote_completion(req, reason)
                client.cancelMktData(req)
                put('acquisition.json', result)
    return result


def final_orders(put, observer_factory=None):
    """One actual audit; exports a whitelist, never its free-form error payloads."""
    from scripts.certification.pr1090_terminal_observation_supervisor import final_broker_audit
    from src.ibkr.transport_diagnostic import TransportDiagnostic
    holder = []
    def observe(client):
        diagnostic = (observer_factory or (lambda c: TransportDiagnostic(c, profile='final-orders')))(client)
        holder.append(diagnostic)
        return diagnostic
    result = None
    try:
        result = final_broker_audit(observer_factory=observe)
        allowed = ('query_completed', 'disconnected', 'query_type', 'timeout_seconds',
                   'end_received', 'elapsed_seconds', 'connected_before_query',
                   'connected_after_wait', 'network_thread_alive_before_query',
                   'network_thread_alive_after_wait', 'open_orders_count', 'mutation_attempts')
        proof = {k: v for k, v in result.items() if k in allowed}
        proof['error_present'] = 'error' in result
        proof['observer_cleanup_failed'] = 'observer_cleanup_error_type' in result
        put('final-order-audit.json', proof)
    finally:
        try:
            transport = holder[0].snapshot() if holder else {'coverage_verified': False, 'absence_claims_valid': False}
        except BaseException:
            transport = {'coverage_verified': False, 'absence_claims_valid': False, 'snapshot_failed': True}
        if result and 'observer_cleanup_error_type' in result:
            transport = dict(transport, coverage_verified=False, absence_claims_valid=False, cleanup_failed=True)
        put('transport-diagnostic.json', transport)
    return bool(result and result['query_completed'] and result['disconnected']), transport


def main():
    args = sys.argv[1:]
    if len(args) not in (3, 5):
        raise RuntimeError('Expected phase/root/commit and optional explicit profile/tree')
    phase, root_text, expected = args[:3]
    profile, expected_tree = args[3:] if len(args) == 5 else ('quotes', None)
    if profile not in ('quotes', 'final-orders'):
        raise RuntimeError('Unknown diagnostic profile')
    if profile == 'final-orders' and (not expected_tree or len(expected_tree) != 40 or
                                     any(c not in '0123456789abcdef' for c in expected_tree)):
        raise RuntimeError('Final orders requires explicit reviewed tree')
    root = Path(root_text); repo = root/'s'; evidence = root/'e'
    sys.path.insert(0, str(repo)); os.chdir(repo)
    from src.ibkr.evidence_safety import install_console_protection, scan_artifacts, write_json
    def put(name, value):
        write_json(evidence/name, value)
    if phase in ('package', 'seal'):
        # Filesystem only. All quote writers must have exited before this phase.
        proof = json.loads((evidence/'privacy-probe.json').read_text(encoding='utf-8'))
        if not proof.get('passed'):
            raise RuntimeError('Probe privacy verification absent/failed; retain local evidence')
        if profile == 'final-orders':
            result = json.loads((evidence/'result.json').read_text(encoding='utf-8'))
            if result.get('scope') != 'FINAL_ORDERS_DIAGNOSTIC_ONLY' or result.get('accepted') != expected:
                raise RuntimeError('Package scope/pin differs')
        shutil.copy2(__file__, evidence/'operator.py')
        scan = scan_artifacts(evidence)
        put('privacy-'+phase+'.json', scan)
        if not scan['passed']:
            raise RuntimeError('Privacy scan failed; no shareable archive')
        if phase == 'package':
            return 0
        archive = root/('final-orders-diagnostic-upload.zip' if profile == 'final-orders' else 'quote-diagnostic-upload.zip')
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
            for path in sorted(evidence.rglob('*')):
                if (evidence/'PACKAGE_STOP_REQUESTED').exists():
                    raise RuntimeError('Package stop requested')
                if path.is_file():
                    z.write(path, path.relative_to(evidence))
        return 0
    if phase != 'probe':
        raise RuntimeError('Unknown phase')
    install_console_protection()
    started = time.monotonic(); timings = []
    def stage(name):
        timings.append({'stage': name, 'utc': datetime.now(timezone.utc).isoformat(),
                        'elapsed_seconds': time.monotonic()-started})
        put('startup-stages.json', timings)
    report = {'status': 'FAIL', 'PAPER_READY': False, 'PAPER_READINESS_GATE': 'FAIL', 'scope': 'FINAL_ORDERS_DIAGNOSTIC_ONLY' if profile == 'final-orders' else 'QUOTE_DIAGNOSTIC_ONLY',
              'accepted': expected, 'operator_sha256': digest(Path(__file__)), 'scanner_attempted': False, 'broker_audit_completed': False,
              'source_state': 'NOT_VERIFIED', 'operator_state': 'NOT_VERIFIED'}
    diagnostic = None
    client = None; before = None; original = None; original_hash = None; rc = 1
    class SilentConsole:
        def write(self, text):
            if diagnostic is not None:
                diagnostic.count('console_writes_suppressed')
            return len(text)
        def flush(self):
            pass
    if profile == 'final-orders':
        # This is a dedicated child. Even a failed/late reader must not write
        # private order details after cleanup or during the final privacy scan.
        # The nested context below restores to these silent process-lifetime sinks.
        sys.stdout = SilentConsole()
        sys.stderr = SilentConsole()
    # Native/SDK exception paths may print arbitrary payloads. The isolated
    # diagnostic retains structured evidence only, never those console strings.
    with contextlib.redirect_stdout(SilentConsole()), contextlib.redirect_stderr(SilentConsole()):
        try:
            stage('entry_imports')
            if os.name != 'nt' or sys.version_info[:3] != (3, 13, 3):
                raise RuntimeError('Requires Windows Python3.13.3')
            if hasattr(sys.modules.get('sitecustomize'), 'offline'):
                raise RuntimeError('Offline hook present; do not acquire')
            # Read literal environment declarations without importing config consumers.
            registry = ast.parse((repo/'src/config/config_registry.py').read_text(encoding='utf-8'))
            defaults = ast.parse((repo/'scripts/certification/pr1040_real_readonly_runtime_observation_adapter.py').read_text(encoding='utf-8'))
            safe = next(ast.literal_eval(n.value) for n in defaults.body if isinstance(n, ast.AnnAssign)
                        and isinstance(n.target, ast.Name) and n.target.id == 'READ_ONLY_ENV_DEFAULTS')
            original = Path(os.environ.get('IBKR_ORDER_ID_STATE_PATH') or Path.home()/'.ibkr_order_id_state.json')
            original_hash = digest(original)
            env = dict(os.environ)
            for node in ast.walk(registry):
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if isinstance(key, ast.Constant) and key.value == 'env':
                            for name in ast.literal_eval(value):
                                env.pop(name, None)
            for key in tuple(env):
                if key.startswith(('PR1090_', 'ROSS_')) or key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP'):
                    env.pop(key, None)
            env.update(safe)
            state = root/'state'; state.mkdir()
            if original.exists():
                shutil.copy2(original, state/'order-id.json')
            env.update(IBKR_HOST='127.0.0.1', IBKR_PORT='7497', IBKR_CLIENT_ID='71',
                IBKR_FALLBACK_ENABLED='false', NEWS_ENABLED='false', NEWS_MAINTENANCE_ENABLED='false',
                ROSS_ISSUER_QUERY_ENABLED='false', IBKR_ORDER_TRANSLATION_ENABLED='false', LIVE_EXECUTION_PROBE_MODE='false',
                IBKR_ORDER_ID_STATE_PATH=str(state/'order-id.json'), IBKR_GUARD_PERSIST_PATH=str(state/'guard.json'),
                PR1090_STOP_FILE=str(evidence/'STOP_REQUESTED'))
            os.environ.clear(); os.environ.update(env)
            from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import assert_safe_runtime_env
            assert_safe_runtime_env(env)
            from scripts.certification import pr1090_terminal_observation_supervisor as safety
            from src.core.acquisition import acquisition_scope, wait_event
            from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
            from src.ibkr.mutation_audit import require_zero_attempts, snapshot
            from src.ibkr.read_only_guard import assert_read_only_allows
            from src.config.system_config import get_current_market_session
            from ibapi.client import EClient
            stage('imports_complete_source_begin')
            safety.require_clean_certification_worktree(expected)
            if profile == 'final-orders':
                actual_tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=repo, timeout=10).decode().strip()
                if actual_tree != expected_tree:
                    raise RuntimeError('Reviewed tree differs')
            before = manifest(repo); put('source-before.json', before)
            stage('source_hashed_inventory')
            inventory = safety.runtime_inventory(); put('initial-runtime-inventory.json', inventory)
            if not inventory['completed'] or inventory['runtimes']:
                raise RuntimeError('Initial runtime inventory unavailable/nonempty')
            if get_current_market_session() != 'RTH':
                raise RuntimeError('Normal configured RTH required; no override')
            for action in ('PLACE_ORDER', 'MODIFY_ORDER', 'CANCEL_ORDER'):
                try:
                    assert_read_only_allows(action)
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError('READ_ONLY guard absent')
            if not all(getattr(getattr(EClient, n), '_mutation_audited', False)
                       for n in ('placeOrder', 'cancelOrder', 'reqGlobalCancel')):
                raise RuntimeError('SDK audit instrumentation absent')
            if not getattr(IbkrClient.submit_order, '_mutation_audited', False):
                raise RuntimeError('Native submission audit instrumentation absent')
            require_zero_attempts(snapshot())
            stage('guards_complete_connect')
            if profile == 'final-orders':
                def order_observer(owned_client):
                    nonlocal diagnostic
                    from src.ibkr.transport_diagnostic import TransportDiagnostic
                    diagnostic = TransportDiagnostic(owned_client, profile='final-orders')
                    return diagnostic
                with acquisition_scope():
                    complete, transport = final_orders(put, observer_factory=order_observer)
                report['broker_audit_completed'] = complete
                report['transport_evidence_incomplete'] = not transport['coverage_verified']
                rc = 0 if complete and transport['coverage_verified'] else 2
                report['status'] = 'DIAGNOSTIC_COMPLETE' if rc == 0 else 'DIAGNOSTIC_ONLY'
            else:
                client = IbkrClient('127.0.0.1', 7497, 71, 5, 'DELAYED', True)
                from src.ibkr.transport_diagnostic import TransportDiagnostic
                diagnostic = TransportDiagnostic(client)
                diagnostic.__enter__()
                with acquisition_scope():
                    client.connect()  # One connection, no manager/reconnect wrapper.
                    diagnostic.record('negotiated', server_version=client.serverVersion())
                    stage('connected_acquisition_begin')
                    report['scanner_attempted'] = True
                    result = acquire(client, put)
                stage('acquisition_finished')
                complete = bool(result['selected'] and len(result['quotes']) == len(result['selected'])
                                and all(q['diagnostic_fields_available'] for q in result['quotes']))
                report['status'] = 'DIAGNOSTIC_COMPLETE' if complete else 'DIAGNOSTIC_ONLY'
                rc = 0 if complete else 2
        except BaseException as exc:
            report.update(status='FAIL', error_type=type(exc).__name__)
            rc = 1
        finally:
            # Finalizers are outside the acquisition deadline/stop scope.
            stage('cleanup_begin')
            if client is not None:
                try:
                    for req in tuple(client._active_market_req_ids):
                        client.cancelMktData(req)
                    if not client.is_connected():
                        raise RuntimeError('Final audit requires existing connection; no reconnect')
                    client._open_orders_event.clear(); client._open_orders_snapshot = {}
                    client.reqAllOpenOrders()
                    if not wait_event(client._open_orders_event, 5) or not client.is_connected():
                        raise RuntimeError('Final audit openOrderEnd missing/connection lost')
                    report['broker_audit_completed'] = True
                    report['open_orders_count'] = len(client._open_orders_snapshot)
                except BaseException as exc:
                    report['cleanup_error_type'] = type(exc).__name__; rc = 1
                finally:
                    try:
                        client.disconnect()
                        thread = client._thread
                        report['disconnected'] = not client.is_connected() and not (thread and thread.is_alive())
                        with client._quote_trace._lock:
                            put('quote-trace.json', {'requests': dict(client._quote_trace.requests),
                                'suppressed_logs': client._quote_trace.suppressed_logs,
                                'evicted_requests': client._quote_trace.evicted_requests,
                                'unknown_callbacks': dict(client._quote_trace.unknown_callbacks)})
                        maps = {name: len(getattr(client, name)) for name in
                            ('_active_market_req_ids', '_market_events', '_market_data', '_ticker_by_req_id', '_req_id_by_contract_key')}
                        put('quote-cleanup.json', maps)
                        if not report['disconnected'] or any(maps.values()):
                            rc = 1
                    except BaseException as exc:
                        report['disconnect_error_type'] = type(exc).__name__; rc = 1
            if diagnostic is not None:
                if profile == 'final-orders':
                    try:
                        diagnostic.close()
                        transport = diagnostic.snapshot()
                        if report.get('transport_evidence_incomplete'):
                            transport = dict(transport, coverage_verified=False, absence_claims_valid=False)
                    except BaseException:
                        transport = {'coverage_verified': False, 'absence_claims_valid': False, 'cleanup_failed': True}
                    if transport.get('cleanup_failed') or transport.get('snapshot_failed'):
                        rc = 1
                else:
                    diagnostic.close()
                    transport = diagnostic.snapshot()
                put('transport-diagnostic.json', transport)
                if not transport['coverage_verified']:
                    report['transport_evidence_incomplete'] = True
                    rc = 1
            try:
                stage('final_source_inventory')
                after = manifest(repo); put('source-after.json', after)
                if before is None or before != after:
                    raise RuntimeError('Source comparison incomplete/changed')
                safety.require_clean_certification_worktree(expected)
                report['source_state'] = 'PASS'
                if original is None or digest(original) != original_hash:
                    raise RuntimeError('Operator state comparison incomplete/changed')
                report['operator_state'] = 'PASS'
                counts = snapshot(); put('mutation-attempts.json', counts); require_zero_attempts(counts)
                final = safety.runtime_inventory(); put('final-runtime-inventory.json', final)
                if not final['completed'] or final['runtimes']:
                    raise RuntimeError('Final runtime inventory incomplete/nonempty')
                report['final_inventory_complete_empty'] = True
            except BaseException as exc:
                report['validation_error_type'] = type(exc).__name__; rc = 1
            report['exit_code'] = rc
            if rc == 1:
                report['status'] = 'FAIL'
            put('result.json', report)
            stage('probe_finished')
    privacy = scan_artifacts(evidence); put('privacy-probe.json', privacy)
    return rc if privacy['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
