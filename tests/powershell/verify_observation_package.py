"""Controlled packaging regressions, run by Windows PowerShell; never launch runtime."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import zipfile

repo, scratch = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo))
from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from src.ibkr.evidence_safety import write_json
from src.ibkr.shutdown_evidence import REQUIRED_HOOKS


def forbidden(*args, **kwargs):
    raise AssertionError('Runtime/broker acquisition forbidden in packaging test')

supervisor.main = forbidden
supervisor.final_broker_audit = forbidden
original_env = dict(os.environ)
for case in ('valid', 'missing-terminal', 'mutation', 'source', 'order-state', 'inventory', 'privacy', 'bad-cache', 'preflight-timeout', 'preflight-late-pass'):
    os.environ.clear()
    os.environ.update(original_env)
    root = scratch / ('real-package-' + case)
    checkout = root / 's'
    evidence = root / 'e'
    state = root / 'state'
    checkout.mkdir(parents=True)
    evidence.mkdir()
    state.mkdir()
    tracked = checkout / 'tracked.txt'
    tracked.write_text('reviewed source')
    subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
    subprocess.run(['git', '-C', str(checkout), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(checkout), '-c', 'user.name=Harness', '-c', 'user.email=harness@example.invalid', 'commit', '-qm', 'fixture'], check=True)
    expected = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    write_json(evidence / 'source-before.json', {'tracked.txt': hashlib.sha256(tracked.read_bytes()).hexdigest()})
    original = root / 'operator-order-id.json'
    original.write_text('{"last_reserved_order_id":361}')
    (root / 'operator-state-source.json').write_text(json.dumps({'path': str(original), 'sha256': hashlib.sha256(original.read_bytes()).hexdigest()}))
    events = ['GRACEFUL_STOP_REQUESTED', 'SHUTDOWN_STARTED', 'SHUTDOWN_COMPLETE', 'TERMINAL_FLUSHED',
              'RUNTIME_PROCESS_EXITED', 'NO_ROSS_RUNTIME', 'FINAL_BROKER_QUERY', 'FINAL_AUDIT_DISCONNECTED', 'FINAL_EVIDENCE_FLUSHED']
    terminal = {'runtime_identity_verified': True, 'launcher_exit_code': 0, 'runtime_exit_code': 0,
                'events': [dict(event=name, sequence=i, monotonic_ns=i+1, completed=True) for i, name in enumerate(events)],
                'hooks': [dict(hook=name, attempted=True, completed=True) for name in REQUIRED_HOOKS],
                'mutation_attempts': dict(place=0, modify=0, cancel=0),
                'audit_mutation_attempts': dict(place=0, modify=0, cancel=0),
                'final_callbacks': {name: dict(attempted=True, completed=True) for name in
                                    ('process_inventory', 'broker_audit', 'artifact_validation', 'mutation_validation')}}
    if case == 'mutation':
        terminal['mutation_attempts']['place'] = 1
    if case not in ('missing-terminal','preflight-timeout','preflight-late-pass'):
        write_json(evidence / 'terminal' / 'terminal_evidence.json', terminal)
    if case == 'preflight-late-pass':
        write_json(evidence/'preflight-result.json', {'status':'PASS','stage':'complete','exit_code':0})
        write_json(evidence/'phase-status-before-package.json', {'preflight_exit':0,
            'preflight_timed_out':True, 'outer_reason':'Preflight timed out; no observation launch.'})
    if case == 'preflight-timeout':
        (evidence/'source-before.json').unlink()
        (root/'operator-state-source.json').unlink()
        write_json(evidence/'preflight-result.json', {'status':'FAIL','stage':'initial_runtime_inventory',
            'exit_code':1,'reason':'Pre-existing runtime or incomplete inventory; no launch.'})
        write_json(evidence/'initial-runtime-inventory.json', {'completed':False,'runtimes':[],'error_type':'TimeoutExpired'})
    if case == 'source':
        tracked.write_text('unreviewed source')
    if case == 'order-state':
        original.write_text('changed')
    if case == 'privacy':
        (evidence / 'leak.txt').write_text('Account DU1234567')
    if case == 'bad-cache':
        (state / 'news.json').write_text('{bad json')
    supervisor.runtime_inventory = lambda: {'completed': True, 'runtimes': [{'pid': 987}] if case == 'inventory' else []}
    sys.argv = ['operator', 'package', str(root), expected]
    code = None
    try:
        runpy.run_path(str(repo / 'scripts/certification/natural_readonly_operator.py'), run_name='__main__')
    except SystemExit as exc:
        code = exc.code
    except json.JSONDecodeError:
        assert case == 'bad-cache'
        code = 'bad-cache'
    if case == 'valid':
        assert code == 0, code
    else:
        assert code != 0, (case, code)
    archive = root / 'ross-natural-readonly-upload.zip'
    if case in ('privacy', 'bad-cache'):
        assert not archive.exists(), case
    else:
        with zipfile.ZipFile(archive) as zipped:
            assert 'operator-summary.json' in zipped.namelist()
            assert not any('order-id' in name or name.endswith('.sqlite3') for name in zipped.namelist())
            summary = json.loads(zipped.read('operator-summary.json'))
            assert summary['terminal_checks_passed'] == (case == 'valid'), case
            assert summary['PAPER_READY'] is False
            if case == 'preflight-late-pass':
                assert summary['preflight_result']['status'] == 'PASS'
                assert summary['preflight_outer_status']['preflight_timed_out'] is True
                assert 'outer process deadline' in summary['blockers'][0]
            if case == 'preflight-timeout':
                assert summary['tracked_source_unchanged'] is None
                assert summary['operator_order_state_unchanged'] is None
                assert summary['source_integrity_status'] == summary['order_state_status'] == 'NOT_VERIFIED'
                assert summary['graceful_shutdown'] is None and summary['terminal_status'] == 'NOT_VERIFIED'
                assert summary['scanner_pass'] == 'NOT_OBSERVED'
                assert summary['blockers'][0].startswith('Preflight initial_runtime_inventory:')
                mutation = json.loads(zipped.read('independent-mutation-validation.json'))
                assert mutation['passed'] is None and mutation['status']=='NOT_VERIFIED'
                assert json.loads(zipped.read('package-result.json'))['expected_exit_code']==2
    if case == 'preflight-timeout':
        write_json(evidence/'phase-status.json', {'preflight_exit':1,'observation_exit':None,'package_exit':2,'final_exit':1})
        sys.argv = ['operator','seal',str(root),expected]
        try:
            runpy.run_path(str(repo/'scripts/certification/natural_readonly_operator.py'),run_name='__main__')
        except SystemExit as exc:
            assert exc.code == 0
        with zipfile.ZipFile(archive) as sealed:
            actual = json.loads(sealed.read('phase-status.json'))
            assert actual['preflight_exit']==1 and actual['package_exit']==2 and actual['observation_exit'] is None
        preserved_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        (evidence/'unsafe-receipt.txt').write_text('Account DU1234567')
        sys.argv = ['operator','seal',str(root),expected]
        try:
            runpy.run_path(str(repo/'scripts/certification/natural_readonly_operator.py'),run_name='__main__')
        except SystemExit as exc:
            assert exc.code != 0
        else:
            raise AssertionError('Unsafe final receipt was sealed')
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == preserved_hash

print('REAL_PACKAGE_CHECKS_PASS: 10 synthetic cases; no acquisition')

if os.name == 'nt':
    # Exercise real preflight with synthetic inventory/session/native classes.
    # Fake SDK classes have no connect/request methods: accidental acquisition fails.
    import shutil
    import types
    from src.config import system_config
    saved_session = system_config.get_current_market_session
    def audited(*args, **kwargs):
        raise AssertionError('No broker operation allowed')
    audited._mutation_audited = True
    class FakeSDK:
        placeOrder = cancelOrder = reqGlobalCancel = audited
    class FakeNative:
        submit_order = audited
    modules = {
        'ibapi.client': types.SimpleNamespace(EClient=FakeSDK),
        'src.adapters.brokers.ibkr.ibkr_client': types.SimpleNamespace(IbkrClient=FakeNative),
    }
    saved_modules = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    for case in ('valid', 'dirty', 'inventory', 'inventory-timeout', 'session'):
        os.environ.clear(); os.environ.update(original_env)
        root = scratch / ('real-preflight-' + case)
        checkout = root / 's'
        hook = checkout / 'scripts/certification/readonly_cache_sitecustomize.py'
        hook.parent.mkdir(parents=True)
        shutil.copy2(repo / 'scripts/certification/readonly_cache_sitecustomize.py', hook)
        subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(checkout), '-c', 'user.name=Harness', '-c', 'user.email=harness@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        expected = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
        if case == 'dirty': hook.write_text('unreviewed')
        supervisor.ROOT = checkout
        supervisor.runtime_inventory = lambda: {'completed':case!='inventory-timeout', 'runtimes':[{'pid':987}] if case=='inventory' else [], **({'error_type':'TimeoutExpired'} if case=='inventory-timeout' else {})}
        system_config.get_current_market_session = lambda: 'CLOSED' if case == 'session' else 'RTH'
        original = root / 'original-order-state.json'
        original.write_text('{"last_reserved_order_id":361}')
        os.environ['IBKR_ORDER_ID_STATE_PATH'] = str(original)
        sys.argv = ['operator', 'preflight', str(root), expected]
        failed = False
        try:
            runpy.run_path(str(repo / 'scripts/certification/natural_readonly_operator.py'), run_name='__main__')
        except (RuntimeError, SystemExit):
            failed = True
        assert failed == (case != 'valid'), case
        if case == 'valid':
            assert json.loads((root / 'state/order-id.json').read_text())['last_reserved_order_id'] == 361
            receipt = json.loads((root / 'e/child-cache-probe.json').read_text())
            assert receipt['exit_code'] == 0 and receipt['parent_ignore_environment'] is True
            assert json.loads((root / 'e/preflight.json').read_text())['write_guards_verified'] is True
            timing = json.loads((root/'e/preflight-timing.json').read_text())['stages']
            assert timing[0]['stage'] == 'python_entry_before_repository_imports'
            assert timing[-1]['stage'] == 'guard_checks_and_baselines_complete'
            assert 'baseline_finalization' in [row['stage'] for row in timing]
            assert [row['elapsed_seconds'] for row in timing] == sorted(row['elapsed_seconds'] for row in timing)
            news = json.loads((root / 'e/news-maintenance-config.json').read_text())
            assert all(news[key] is True for key in ('NEWS_ENABLED','NEWS_MAINTENANCE_ENABLED','ROSS_ISSUER_QUERY_ENABLED'))
            assert news['NEWS_REFRESH_SECONDS_RTH'] == 120 and news['NEWS_TOTAL_BUDGET_S'] == 8
        else:
            assert not (root / 'e/preflight.json').exists()
            failure = json.loads((root/'e/preflight-result.json').read_text())
            assert failure['status']=='FAIL' and failure['exit_code'] != 0
            if case == 'inventory-timeout':
                assert failure['stage']=='initial_runtime_inventory'
                assert not (root/'e/source-before.json').exists()
                assert not (root/'operator-state-source.json').exists()
    for name, module in saved_modules.items():
        if module is None: sys.modules.pop(name, None)
        else: sys.modules[name] = module
    system_config.get_current_market_session = saved_session
    print('REAL_PREFLIGHT_CHECKS_PASS: 5 synthetic cases; no acquisition')
