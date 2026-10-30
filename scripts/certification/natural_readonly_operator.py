# Operator-only filesystem/preflight/observation phases. Not imported by production.
import hashlib, json, os, shutil, subprocess, sys, zipfile, time
from datetime import datetime, timezone
from pathlib import Path
phase, root_text, expected, *duration_args = sys.argv[1:]
if len(duration_args) > 1:
    raise SystemExit('At most one bounded runtime duration is allowed')
runtime_seconds = int(duration_args[0]) if duration_args else 180
if not 180 <= runtime_seconds <= 1800:
    raise SystemExit('Runtime duration must be between180 and1800 seconds')
if phase not in ('prepare', 'preflight', 'observe', 'package', 'seal'):
    raise SystemExit('Unknown operator phase')
root = Path(root_text); repo = root/'s'; evidence = root/'e'; state = root/'state'
# Bootstrap and import costs are inside the outer process budget. Record them
# before repository imports; no provider/broker operation is performed here.
_timing_started = time.monotonic()
_timing_rows = []
def preflight_timing(stage):
    if phase not in ('prepare', 'preflight', 'package'):
        return
    timing_dir = root/'preparation' if phase == 'prepare' else evidence
    timing_dir.mkdir(parents=True, exist_ok=True)
    _timing_rows.append({'stage': stage, 'utc': datetime.now(timezone.utc).isoformat(),
                         'elapsed_seconds': time.monotonic() - _timing_started})
    target = timing_dir/(phase+'-timing.json')
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({'pid': os.getpid(), 'stages': _timing_rows}, indent=2))
    temporary.replace(target)
preflight_timing('python_entry_before_repository_imports')
sys.path.insert(0, str(repo)); os.chdir(repo)
if hasattr(sys.modules.get('sitecustomize'), 'offline'):
    raise SystemExit('Offline pytest hook present: observation must use a separate process.')
from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import build_safe_readonly_env, assert_safe_runtime_env
from src.config.config_registry import CONFIG_REGISTRY
preflight_timing('adapter_and_registry_imports_complete')
env = dict(os.environ)
env.pop('PR1108_CACHE_PROBE_TRACE', None)
env.pop('PYTHONHOME', None)
env.pop('PYTHONSTARTUP', None)
for entry in CONFIG_REGISTRY.values():
    for key in entry.get('env', ()):
        env.pop(key, None)
for key in tuple(env):
    if key.startswith('PR1090_') or key.startswith('ROSS_'):
        env.pop(key, None)
env = build_safe_readonly_env(env)
env.update(PYTHONPATH=os.pathsep.join((str(state/'startup'),str(repo))), PYTHONUNBUFFERED='1',
    PR1108_YFINANCE_CACHE=str(state/'yfinance'),
    IBKR_HOST='127.0.0.1', IBKR_PORT='7497', IBKR_CLIENT_ID='71',
    IBKR_ORDER_TRANSLATION_ENABLED='false', LIVE_EXECUTION_PROBE_MODE='false',
    IBKR_FALLBACK_ENABLED='false', ROSS_ISSUER_QUERY_ENABLED='true', ROSS_REQUIRE_NEWS='true',
    NEWS_ENABLED='true', NEWS_MAINTENANCE_ENABLED='true',
    SCANNER_TOP_GAINERS_COUNT='50', TOPN_MAX_SYMBOLS_PER_STRATEGY='50',
    WATCHLIST_MAX_SYMBOLS_PER_STRATEGY='15', FOCUS_MAX_SYMBOLS_PER_STRATEGY='5',
    IBKR_ORDER_ID_STATE_PATH=str(state/'order-id.json'),
    IBKR_GUARD_PERSIST_PATH=str(state/'submission-guard.json'),
    SCANNER_FLOAT_CACHE_FILE=str(state/'float.json'), NEWS_CACHE_FILE=str(state/'news.json'),
    PERSISTENCE_SQLITE_PATH=str(state/'runtime.sqlite3'), DECISION_TRACE_PATH=str(state/'decision-trace.jsonl'))
assert_safe_runtime_env(env)
original_state = Path(os.environ.get('IBKR_ORDER_ID_STATE_PATH') or Path.home()/'.ibkr_order_id_state.json')
os.environ.clear(); os.environ.update(env)
from src.ibkr.evidence_safety import capture_console, install_console_protection, scan_artifacts, write_json
from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from src.ibkr.mutation_audit import require_zero_attempts, snapshot
preflight_timing('supervisor_imports_complete')
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
def check_stop():
    stops = {'prepare': root/'preparation/STOP_REQUESTED', 'preflight': evidence/'preflight.stop',
             'package': evidence/'package.stop', 'seal': root/'seal.stop'}
    if phase in stops and stops[phase].exists():
        raise SystemExit('Owned phase stop requested; no admission.')

def source_manifest():
    preflight_timing('source_enumeration_begin')
    check_stop()
    paths = subprocess.check_output(['git','ls-files','-z'], cwd=repo).decode().split('\0')
    preflight_timing('source_enumeration_complete_hashing_begin')
    manifest = {}
    for name in paths:
        check_stop()
        if name:
            manifest[name] = digest(repo/name)
    check_stop()
    preflight_timing('source_hashing_complete')
    return manifest
# These records are local bindings, never reusable admission authority.
def canonical_config(value):
    # Registry calendars contain sets; repr(set) is process/hash-seed dependent.
    if isinstance(value, dict):
        return {str(key): canonical_config(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (set, frozenset)):
        return sorted((canonical_config(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [canonical_config(item) for item in value]
    if hasattr(value, 'isoformat'):
        return {'type': type(value).__name__, 'iso': value.isoformat()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError('Unsupported configuration binding type')

def binding():
    from src.config.config_resolver import get_config
    actual_head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
    if actual_head != expected:
        raise SystemExit('Pinned source root does not match expected commit.')
    return {'root': str(root.resolve()), 'head': actual_head,
        'tree': subprocess.check_output(['git','rev-parse','HEAD^{tree}'], cwd=repo, text=True).strip(),
        'seconds': runtime_seconds, 'config': {key: canonical_config(get_config(key)) for key in CONFIG_REGISTRY},
        'hook': digest(state/'startup/sitecustomize.py'),
        'hook_source': digest(repo/'scripts/certification/readonly_cache_sitecustomize.py'),
        'python': str(Path(sys.executable).resolve())}

def complete_manifest():
    manifest = source_manifest()
    if not manifest or any(value is None for value in manifest.values()):
        raise SystemExit('Tracked source missing or not a regular readable file.')
    return manifest

def require_prepared():
    saved = json.loads((root/'preparation/prepared.json').read_text())
    if saved['binding'] != binding():
        raise SystemExit('Preparation root/pin/tree/config/hook/duration binding changed.')
    receipt = json.loads((root/'preparation/prepare-process.process.json').read_text(encoding='utf-8-sig'))
    if not (receipt['exited'] and receipt['timely_exit_verified'] and receipt['exit_code'] == 0):
        raise SystemExit('Preparation OS exit is not verified timely success.')
    if saved['binding']['hook'] != saved['binding']['hook_source']:
        raise SystemExit('Prepared hook differs from tracked hook source.')
    return saved

def session_check():
    from src.config.system_config import get_current_market_session
    now = datetime.now(timezone.utc)
    # Same configured calendar/session owner, including holidays and early close.
    # Reserve the whole supervisor envelope, not just runtime, before RTH ends.
    from datetime import timedelta
    if (get_current_market_session(now) != 'RTH' or
            get_current_market_session(now + timedelta(seconds=runtime_seconds + 360)) != 'RTH'):
        raise SystemExit('Requires normal configured RTH with runtime and finalization time remaining; no session override.')

def verify_write_guards():
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    from ibapi.client import EClient
    from src.ibkr.read_only_guard import assert_read_only_allows
    for action in ('PLACE_ORDER','MODIFY_ORDER','CANCEL_ORDER'):
        try: assert_read_only_allows(action)
        except RuntimeError: pass
        else: raise SystemExit('Write guard not enforced.')
    if not all(getattr(getattr(EClient, name), '_mutation_audited', False)
               for name in ('placeOrder','cancelOrder','reqGlobalCancel')):
        raise SystemExit('Independent SDK attempt instrumentation missing.')
    if not getattr(IbkrClient.submit_order, '_mutation_audited', False):
        raise SystemExit('Native submit-order attempt instrumentation missing.')
    require_zero_attempts(snapshot())

def operator_unchanged():
    saved = json.loads((root/'operator-state-source.json').read_text())
    return digest(Path(saved['path'])) == saved['sha256']

def require_controller():
    controller = json.loads((root/'runner.json').read_text(encoding='utf-8-sig'))
    if controller['token'] != os.environ.get('READONLY_ADMISSION_TOKEN'):
        raise SystemExit('Admission requires the original live runner; no resume.')
    parent = os.getppid()
    if os.name == 'nt':
        from src.runtime.process_identity import WindowsProcessHandle, read_process_identity
        # Reuse retained-handle/OS identity owners; venv redirectors may intervene.
        handle = WindowsProcessHandle(controller['pid'], controller['creation_token'])
        try:
            if handle.poll() is not None:
                raise SystemExit('Admission controller exited.')
            deadline = time.monotonic() + 3
            for _ in range(4):
                if parent == controller['pid']:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SystemExit('Controller ancestry deadline expired.')
                parent = read_process_identity(parent, timeout=remaining)['parent_pid']
            if parent != controller['pid'] or handle.poll() is not None:
                raise SystemExit('Admission controller ancestry unavailable.')
        finally:
            handle.close()
    elif parent != controller['pid']:
        raise SystemExit('Admission controller changed.')
    return controller

if phase == 'prepare':
    preparation = root/'preparation'
    if (preparation/'prepared.json').exists() or evidence.exists() or state.exists():
        raise SystemExit('Preparation already attempted; fresh root required.')
    if os.name != 'nt' or sys.version_info[:3] != (3, 13, 3):
        raise SystemExit('Requires the accepted Windows Python 3.13.3 interpreter.')
    supervisor.require_clean_certification_worktree(expected)
    state.mkdir()
    startup = state/'startup'; startup.mkdir()
    shutil.copy2(repo/'scripts/certification/readonly_cache_sitecustomize.py', startup/'sitecustomize.py')
    m0 = complete_manifest()
    write_json(preparation/'source-prepared.json', m0)
    write_json(preparation/'prepared.json', {'binding': binding(), 'comparison_only': True})
elif phase == 'preflight':
    preflight_stage = 'initialization'
    try:
        evidence.mkdir(exist_ok=True)
        require_controller()
        prepared = require_prepared()
        with capture_console(evidence/'preflight'):
            preflight_stage = 'platform'
            preflight_timing(preflight_stage)
            if os.name != 'nt' or sys.version_info[:3] != (3, 13, 3):
                raise SystemExit('Requires the accepted Windows Python 3.13.3 interpreter.')
            preflight_stage = 'source_integrity'
            preflight_timing(preflight_stage)
            supervisor.require_clean_certification_worktree(expected)
            preflight_stage = 'initial_runtime_inventory'
            preflight_timing(preflight_stage)
            inventory = supervisor.runtime_inventory()
            write_json(evidence/'initial-runtime-inventory.json', inventory)
            if not inventory['completed']:
                raise SystemExit('Initial runtime inventory incomplete: '+inventory.get('error_type','UNKNOWN')+
                    '; elapsed='+str(inventory.get('elapsed_seconds','unknown'))+
                    's; timeout='+str(inventory.get('timeout_seconds',15))+'s; no launch.')
            if inventory['runtimes']:
                raise SystemExit('Pre-existing Ross runtime; no launch.')
            preflight_stage = 'session'
            preflight_timing(preflight_stage)
            from src.config.config_resolver import get_config
            session_check()
            preflight_stage = 'news_maintenance_configuration'
            preflight_timing(preflight_stage)
            news_config = {key:get_config(key) for key in ('NEWS_ENABLED','NEWS_MAINTENANCE_ENABLED',
                          'ROSS_ISSUER_QUERY_ENABLED','NEWS_REFRESH_SECONDS_RTH','NEWS_TOTAL_BUDGET_S')}
            if not all(news_config[key] is True for key in ('NEWS_ENABLED','NEWS_MAINTENANCE_ENABLED','ROSS_ISSUER_QUERY_ENABLED')):
                raise SystemExit('Canonical news maintenance configuration not enabled; no launch.')
            write_json(evidence/'news-maintenance-config.json', news_config)
            preflight_stage = 'write_guards'
            preflight_timing(preflight_stage)
            verify_write_guards()
            # Cache-location configuration only. Child startup must fail closed if
            # this cannot be installed; no provider fetch or event-loop-policy edit.
            preflight_stage = 'child_cache_isolation'
            preflight_timing(preflight_stage)
            hook = state/'startup/sitecustomize.py'
            from scripts.certification.readonly_cache_probe import run_cache_probe
            run_cache_probe(sys.executable, repo, evidence, env)
            write_json(evidence/'operator-startup-config.json', {'scope': 'yfinance cache location only',
                'sha256': digest(hook), 'source': hook.read_text(), 'path': str(hook)})
            preflight_stage = 'baseline_finalization'
            preflight_timing(preflight_stage)
            m1 = complete_manifest()
            if m1 != json.loads((root/'preparation/source-prepared.json').read_text()):
                raise SystemExit('Fresh source M1 differs from M0; preparation is never refreshed.')
            supervisor.require_clean_certification_worktree(expected)
            if prepared['binding'] != binding():
                raise SystemExit('Final guard/config/hook binding changed.')
            session_check()
            inventory = supervisor.runtime_inventory()
            write_json(evidence/'admission-runtime-inventory.json', inventory)
            if not inventory['completed'] or inventory['runtimes']:
                raise SystemExit('Final runtime inventory unavailable or occupied.')
            verify_write_guards()
            preflight_timing('operator_state_begin')
            if original_state.exists():
                shutil.copy2(original_state, state/'order-id.json')
            (root/'operator-state-source.json').write_text(json.dumps({'path': str(original_state), 'sha256': digest(original_state)}))
            preflight_timing('operator_state_complete')
            if original_state.exists() and digest(state/'order-id.json') != digest(original_state):
                raise SystemExit('Operator state changed during capture.')
            write_json(evidence/'source-before.json', m1)
            preflight_timing('source_before_persisted')
            write_json(evidence/'preflight.json', {'head': expected, 'utc': datetime.now(timezone.utc).isoformat(),
                'mode': 'READ_ONLY', 'seconds': runtime_seconds, 'top_n': get_config('TOPN_MAX_SYMBOLS_PER_STRATEGY'),
                'watchlist_k': get_config('WATCHLIST_MAX_SYMBOLS_PER_STRATEGY'), 'focus_m': get_config('FOCUS_MAX_SYMBOLS_PER_STRATEGY'),
                'issuer_query': get_config('ROSS_ISSUER_QUERY_ENABLED'), 'require_news': get_config('ROSS_REQUIRE_NEWS'),
                'write_guards_verified': True, 'sdk_attempt_audit_verified': True, 'PAPER_READY': False})
        preflight_timing('guard_checks_and_baselines_complete')
        write_json(evidence/'preflight-result.json', {'status':'PASS', 'stage':'complete', 'exit_code':0})
        write_json(root/'admission.json', {'binding': binding(), 'controller': require_controller(),
            'operator_receipt': digest(root/'operator-state-source.json'),
            'issued_monotonic': time.monotonic(), 'issued_utc': time.time()})
    except BaseException as exc:
        code = exc.code if isinstance(exc, SystemExit) and isinstance(exc.code, int) else 1
        failure = {'status':'FAIL', 'stage':preflight_stage,
            'exit_code':code, 'error_type':type(exc).__name__,
            'reason':str(exc) if isinstance(exc, SystemExit) else type(exc).__name__,
            'observation_started':False}
        try:
            write_json(evidence/'preflight-result.json', failure)
        except OSError:
            print('Preflight initialization/reporting failed; no observation launch.', file=sys.stderr)
        raise
elif phase == 'observe':
    controller = require_controller()
    admission = json.loads((root/'admission.json').read_text())
    outer = json.loads((evidence/'preflight-process.process.json').read_text(encoding='utf-8-sig'))
    result = json.loads((evidence/'preflight-result.json').read_text())
    if not (outer['exited'] and outer['timely_exit_verified'] and outer['exit_code'] == 0 and result['status'] == 'PASS'):
        raise SystemExit('Preflight OS admission not verified.')
    elapsed = time.monotonic() - admission['issued_monotonic']
    if not 0 <= elapsed <= 15 or not 0 <= time.time() - admission['issued_utc'] <= 15:
        raise SystemExit('Admission stale; no delayed or resumed launch.')
    if admission['binding'] != binding() or admission['controller'] != controller:
        raise SystemExit('Admission binding changed.')
    require_prepared()
    supervisor.require_clean_certification_worktree(expected)
    if admission['operator_receipt'] != digest(root/'operator-state-source.json') or not operator_unchanged():
        raise SystemExit('Operator state changed before launch.')
    session_check()
    # Exclusive single-use claim; an interrupted attempt cannot resume.
    with (root/'admission-consumed').open('x') as claim:
        claim.write('consumed')
    check_stop()
    preflight_receipt = json.loads((evidence/'preflight.json').read_text())
    if preflight_receipt.get('seconds') != runtime_seconds or preflight_receipt.get('head') != expected:
        raise SystemExit('Observation duration/head differs from successful preflight')
    install_console_protection()
    write_json(evidence/'observation-attempt.json', {'attempted':True})
    raise SystemExit(supervisor.main(['--seconds',str(runtime_seconds),'--output',str(evidence/'terminal'),'--expected-commit',expected]))
elif phase == 'package':
    # This phase performs filesystem/process checks only. Broker audit belongs
    # exclusively to the existing supervisor after its observed runtime exits.
    evidence.mkdir(exist_ok=True)
    probe_path = evidence/'child-cache-probe.json'
    if probe_path.exists() and json.loads(probe_path.read_text()).get('child_exited') is False:
        raise SystemExit('Cache probe still alive; preserve raw evidence, no archive.')
    with capture_console(evidence/'packaging'):
        preflight_timing('packaging_begin')
        after = complete_manifest()
        before_path = evidence/'source-before.json'
        preflight_timing('package_source_identity_begin')
        actual_head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
        clean = not subprocess.check_output(['git','status','--porcelain'], cwd=repo, text=True).strip()
        unchanged = None if not before_path.exists() else (actual_head == expected and clean and before_path.exists()
                     and json.loads(before_path.read_text()) == after
                     and json.loads((root/'preparation/source-prepared.json').read_text()) == after)
        write_json(evidence/'source-after.json', after)
        preflight_timing('source_after_persisted_inventory_begin')
        inventory = supervisor.runtime_inventory()
        write_json(evidence/'independent-final-runtime-inventory.json', inventory)
        preflight_timing('package_inventory_complete_validation_begin')
        preflight_result_path = evidence/'preflight-result.json'
        preflight_result = json.loads(preflight_result_path.read_text()) if preflight_result_path.exists() else None
        attempted = (evidence/'observation-attempt.json').exists() or (evidence/'terminal').exists()
        terminal_present = (evidence/'terminal'/'terminal_evidence.json').exists()
        mutation_ok = False if terminal_present else None
        blockers = []
        try:
            terminal = json.loads((evidence/'terminal'/'terminal_evidence.json').read_text())
            from src.ibkr.shutdown_evidence import validate_terminal
            require_zero_attempts(terminal.get('mutation_attempts'))
            require_zero_attempts(terminal.get('audit_mutation_attempts'))
            verdict = validate_terminal(terminal)
            mutation_ok = True
            blockers = verdict['blockers']
        except Exception as exc:
            blockers = ['Missing/unsafe terminal evidence: '+type(exc).__name__]
        outer_path = evidence/'phase-status-before-package.json'
        outer_status = json.loads(outer_path.read_text(encoding='utf-8-sig')) if outer_path.exists() else {}
        if outer_status.get('preflight_timed_out'):
            blockers.insert(0, 'Preflight outer process deadline expired; inner guard PASS is not timely-completion authority.')
        if preflight_result and preflight_result.get('status') == 'FAIL':
            blockers.insert(0, 'Preflight '+preflight_result['stage']+': '+preflight_result['reason'])
        write_json(evidence/'independent-mutation-validation.json', {'passed': mutation_ok,
            'status':'NOT_VERIFIED' if mutation_ok is None else ('PASS' if mutation_ok else 'FAIL'),
            'authority': 'runtime SDK pre-guard counters AND separate supervisor audit counters',
            'not_inferred_from_zero_open_orders': True})
        preflight_timing('package_operator_state_begin')
        saved = root/'operator-state-source.json'
        operator_unchanged = None
        if saved.exists():
            original = json.loads(saved.read_text())
            operator_unchanged = digest(Path(original['path'])) == original['sha256']
        preflight_timing('package_operator_state_complete')
        for name in ('news.json', 'float.json'):
            path = state/name
            if path.is_file():
                write_json(evidence/'cache-exports'/name, json.loads(path.read_text()))
        terminal_ok = bool(mutation_ok and not blockers and unchanged and operator_unchanged and inventory['completed'] and not inventory['runtimes'])
        write_json(evidence/'operator-summary.json', {'head': expected, 'graceful_shutdown': terminal_ok if terminal_present else None, 'terminal_status':'NOT_VERIFIED' if not terminal_present else ('PASS' if terminal_ok else 'FAIL'), 'terminal_checks_passed': terminal_ok,
            'preflight_result':preflight_result, 'preflight_outer_status':outer_status, 'observation_attempted':attempted,
            'source_integrity_status':'NOT_VERIFIED' if unchanged is None else ('PASS' if unchanged else 'FAIL'),
            'order_state_status':'NOT_VERIFIED' if operator_unchanged is None else ('PASS' if operator_unchanged else 'FAIL'),
            'tracked_source_unchanged': unchanged, 'operator_order_state_unchanged': operator_unchanged,
            'blockers': blockers, 'scanner_pass': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'), 'natural_issuer_acquisition': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'),
            'catalyst': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'), 'downstream_progression': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'), 'PAPER_READY': False})
    preflight_timing('privacy_scan_begin')
    privacy = scan_artifacts(evidence)
    write_json(evidence/'shareable-evidence-scan.json', privacy)
    if not privacy['passed']:
        raise SystemExit('Privacy scan failed; evidence retained locally, no shareable ZIP.')
    write_json(evidence/'package-result.json', {'status':'PASS' if terminal_ok else 'DIAGNOSTIC_ONLY',
        'expected_exit_code':0 if terminal_ok else 2, 'privacy_scan_passed':True})
    preflight_timing('privacy_scan_complete_archive_begin')
    archive = root/'ross-natural-readonly-upload.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as out:
        for path in sorted(evidence.rglob('*')):
            if path.is_file(): out.write(path, path.relative_to(evidence))
    # The runner alone announces the archive after successful sealing.
    raise SystemExit(0 if terminal_ok else 2)
elif phase == 'seal':
    # Filesystem-only final archive rebuild, after package process/readers exit.
    # The receipt contains retained actual preflight/observation/package exits.
    status = json.loads((evidence/'phase-status.json').read_text(encoding='utf-8-sig'))
    if status.get('package_exit') not in (0, 2):
        raise SystemExit('Cannot seal an unsuccessful packaging process.')
    privacy = scan_artifacts(evidence)
    write_json(evidence/'shareable-evidence-scan.json', privacy)
    if not privacy['passed']:
        raise SystemExit('Final receipt privacy scan failed; no shareable ZIP announcement.')
    archive = root/'ross-natural-readonly-upload.zip'
    temporary = root/'ross-natural-readonly-upload.sealing.zip'
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as out:
        for path in sorted(evidence.rglob('*')):
            if path.is_file(): out.write(path, path.relative_to(evidence))
    os.replace(temporary, archive)
    raise SystemExit(0)
else:
    raise SystemExit('Unknown operator phase')