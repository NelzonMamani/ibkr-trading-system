# Operator-only filesystem/preflight/observation phases. Not imported by production.
import hashlib, json, os, shutil, subprocess, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
phase, root_text, expected, *duration_args = sys.argv[1:]
if len(duration_args) > 1:
    raise SystemExit('At most one bounded runtime duration is allowed')
runtime_seconds = int(duration_args[0]) if duration_args else 180
if not 180 <= runtime_seconds <= 1800:
    raise SystemExit('Runtime duration must be between180 and1800 seconds')
if phase not in ('preflight', 'observe', 'package', 'seal'):
    raise SystemExit('Unknown operator phase')
root = Path(root_text); repo = root/'s'; evidence = root/'e'; state = root/'state'
sys.path.insert(0, str(repo)); os.chdir(repo)
if hasattr(sys.modules.get('sitecustomize'), 'offline'):
    raise SystemExit('Offline pytest hook present: observation must use a separate process.')
from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import build_safe_readonly_env, assert_safe_runtime_env
from src.config.config_registry import CONFIG_REGISTRY
env = dict(os.environ)
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
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
def source_manifest():
    paths = subprocess.check_output(['git','ls-files','-z'], cwd=repo).decode().split('\0')
    return {name: digest(repo/name) for name in paths if name}
if phase == 'preflight':
    preflight_stage = 'initialization'
    try:
        evidence.mkdir(exist_ok=True); state.mkdir()
        with capture_console(evidence/'preflight'):
            preflight_stage = 'platform'
            if os.name != 'nt' or sys.version_info[:3] != (3, 13, 3):
                raise SystemExit('Requires the accepted Windows Python 3.13.3 interpreter.')
            preflight_stage = 'source_integrity'
            supervisor.require_clean_certification_worktree(expected)
            preflight_stage = 'initial_runtime_inventory'
            inventory = supervisor.runtime_inventory()
            write_json(evidence/'initial-runtime-inventory.json', inventory)
            if not inventory['completed']:
                raise SystemExit('Initial runtime inventory incomplete: '+inventory.get('error_type','UNKNOWN')+
                    '; elapsed='+str(inventory.get('elapsed_seconds','unknown'))+
                    's; timeout='+str(inventory.get('timeout_seconds',15))+'s; no launch.')
            if inventory['runtimes']:
                raise SystemExit('Pre-existing Ross runtime; no launch.')
            preflight_stage = 'session'
            from src.config.config_resolver import get_config
            from src.config.system_config import get_current_market_session
            if get_current_market_session() != 'RTH':
                raise SystemExit('Requires the normal configured RTH window; no session override.')
            preflight_stage = 'news_maintenance_configuration'
            news_config = {key:get_config(key) for key in ('NEWS_ENABLED','NEWS_MAINTENANCE_ENABLED',
                          'ROSS_ISSUER_QUERY_ENABLED','NEWS_REFRESH_SECONDS_RTH','NEWS_TOTAL_BUDGET_S')}
            if not all(news_config[key] is True for key in ('NEWS_ENABLED','NEWS_MAINTENANCE_ENABLED','ROSS_ISSUER_QUERY_ENABLED')):
                raise SystemExit('Canonical news maintenance configuration not enabled; no launch.')
            write_json(evidence/'news-maintenance-config.json', news_config)
            preflight_stage = 'write_guards'
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
            # Cache-location configuration only. Child startup must fail closed if
            # this cannot be installed; no provider fetch or event-loop-policy edit.
            preflight_stage = 'child_cache_isolation'
            startup = state/'startup'; startup.mkdir()
            hook = startup/'sitecustomize.py'
            shutil.copy2(repo/'scripts/certification/readonly_cache_sitecustomize.py', hook)
            probe = subprocess.run([sys.executable, '-c',
                "import os, pathlib, yfinance.cache as c; "
                "assert getattr(c, '_readonly_cache_isolated', False); "
                "assert pathlib.Path(os.environ['PR1108_YFINANCE_CACHE']).is_absolute(); "
                "print('CHILD_CACHE_ISOLATION_VERIFIED', c._readonly_cache_locations)"],
                env=env, cwd=repo, capture_output=True, text=True, timeout=30)
            write_json(evidence/'child-cache-probe.json', {'exit_code': probe.returncode,
                'stdout': probe.stdout, 'stderr': probe.stderr, 'child_flags': ['-c'],
                'parent_ignore_environment': bool(sys.flags.ignore_environment)})
            if probe.returncode != 0 or 'CHILD_CACHE_ISOLATION_VERIFIED' not in probe.stdout:
                raise SystemExit('Child startup/cache isolation failed; no runtime launch.')
            write_json(evidence/'operator-startup-config.json', {'scope': 'yfinance cache location only',
                'sha256': digest(hook), 'source': hook.read_text(), 'path': str(hook)})
            preflight_stage = 'baseline_finalization'
            if original_state.exists():
                shutil.copy2(original_state, state/'order-id.json')
            (root/'operator-state-source.json').write_text(json.dumps({'path': str(original_state), 'sha256': digest(original_state)}))
            write_json(evidence/'source-before.json', source_manifest())
            write_json(evidence/'preflight.json', {'head': expected, 'utc': datetime.now(timezone.utc).isoformat(),
                'mode': 'READ_ONLY', 'seconds': runtime_seconds, 'top_n': get_config('TOPN_MAX_SYMBOLS_PER_STRATEGY'),
                'watchlist_k': get_config('WATCHLIST_MAX_SYMBOLS_PER_STRATEGY'), 'focus_m': get_config('FOCUS_MAX_SYMBOLS_PER_STRATEGY'),
                'issuer_query': get_config('ROSS_ISSUER_QUERY_ENABLED'), 'require_news': get_config('ROSS_REQUIRE_NEWS'),
                'write_guards_verified': True, 'sdk_attempt_audit_verified': True, 'PAPER_READY': False})
        write_json(evidence/'preflight-result.json', {'status':'PASS', 'stage':'complete', 'exit_code':0})
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
    with capture_console(evidence/'packaging'):
        after = source_manifest()
        before_path = evidence/'source-before.json'
        actual_head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
        clean = not subprocess.check_output(['git','status','--porcelain'], cwd=repo, text=True).strip()
        unchanged = None if not before_path.exists() else (actual_head == expected and clean and before_path.exists()
                     and json.loads(before_path.read_text()) == after)
        write_json(evidence/'source-after.json', after)
        inventory = supervisor.runtime_inventory()
        write_json(evidence/'independent-final-runtime-inventory.json', inventory)
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
        if preflight_result and preflight_result.get('status') == 'FAIL':
            blockers.insert(0, 'Preflight '+preflight_result['stage']+': '+preflight_result['reason'])
        write_json(evidence/'independent-mutation-validation.json', {'passed': mutation_ok,
            'status':'NOT_VERIFIED' if mutation_ok is None else ('PASS' if mutation_ok else 'FAIL'),
            'authority': 'runtime SDK pre-guard counters AND separate supervisor audit counters',
            'not_inferred_from_zero_open_orders': True})
        saved = root/'operator-state-source.json'
        operator_unchanged = None
        if saved.exists():
            original = json.loads(saved.read_text())
            operator_unchanged = digest(Path(original['path'])) == original['sha256']
        for name in ('news.json', 'float.json'):
            path = state/name
            if path.is_file():
                write_json(evidence/'cache-exports'/name, json.loads(path.read_text()))
        terminal_ok = bool(mutation_ok and not blockers and unchanged and operator_unchanged and inventory['completed'] and not inventory['runtimes'])
        write_json(evidence/'operator-summary.json', {'head': expected, 'graceful_shutdown': terminal_ok if terminal_present else None, 'terminal_status':'NOT_VERIFIED' if not terminal_present else ('PASS' if terminal_ok else 'FAIL'), 'terminal_checks_passed': terminal_ok,
            'preflight_result':preflight_result, 'observation_attempted':attempted,
            'source_integrity_status':'NOT_VERIFIED' if unchanged is None else ('PASS' if unchanged else 'FAIL'),
            'order_state_status':'NOT_VERIFIED' if operator_unchanged is None else ('PASS' if operator_unchanged else 'FAIL'),
            'tracked_source_unchanged': unchanged, 'operator_order_state_unchanged': operator_unchanged,
            'blockers': blockers, 'scanner_pass': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'), 'natural_issuer_acquisition': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'),
            'catalyst': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'), 'downstream_progression': ('REQUIRES_LOG_REVIEW' if attempted else 'NOT_OBSERVED'), 'PAPER_READY': False})
    privacy = scan_artifacts(evidence)
    write_json(evidence/'shareable-evidence-scan.json', privacy)
    if not privacy['passed']:
        raise SystemExit('Privacy scan failed; evidence retained locally, no shareable ZIP.')
    write_json(evidence/'package-result.json', {'status':'PASS' if terminal_ok else 'DIAGNOSTIC_ONLY',
        'expected_exit_code':0 if terminal_ok else 2, 'privacy_scan_passed':True})
    archive = root/'ross-natural-readonly-upload.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as out:
        for path in sorted(evidence.rglob('*')):
            if path.is_file(): out.write(path, path.relative_to(evidence))
    print('SHARE ZIP: '+str(archive))
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