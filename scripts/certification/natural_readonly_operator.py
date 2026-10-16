# Operator-only filesystem/preflight/observation phases. Not imported by production.
import hashlib, json, os, shutil, subprocess, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
phase, root_text, expected = sys.argv[1:]
if phase not in ('preflight', 'observe', 'package'):
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
    evidence.mkdir(exist_ok=True); state.mkdir()
    with capture_console(evidence/'preflight'):
        if os.name != 'nt' or sys.version_info[:3] != (3, 13, 3):
            raise SystemExit('Requires the accepted Windows Python 3.13.3 interpreter.')
        supervisor.require_clean_certification_worktree(expected)
        inventory = supervisor.runtime_inventory()
        write_json(evidence/'initial-runtime-inventory.json', inventory)
        if not inventory['completed'] or inventory['runtimes']:
            raise SystemExit('Pre-existing runtime or incomplete inventory; no launch.')
        from src.config.config_resolver import get_config
        from src.config.system_config import get_current_market_session
        if get_current_market_session() != 'RTH':
            raise SystemExit('Requires the normal configured RTH window; no session override.')
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
        if original_state.exists():
            shutil.copy2(original_state, state/'order-id.json')
        (root/'operator-state-source.json').write_text(json.dumps({'path': str(original_state), 'sha256': digest(original_state)}))
        write_json(evidence/'source-before.json', source_manifest())
        write_json(evidence/'preflight.json', {'head': expected, 'utc': datetime.now(timezone.utc).isoformat(),
            'mode': 'READ_ONLY', 'seconds': 180, 'top_n': get_config('TOPN_MAX_SYMBOLS_PER_STRATEGY'),
            'watchlist_k': get_config('WATCHLIST_MAX_SYMBOLS_PER_STRATEGY'), 'focus_m': get_config('FOCUS_MAX_SYMBOLS_PER_STRATEGY'),
            'issuer_query': get_config('ROSS_ISSUER_QUERY_ENABLED'), 'require_news': get_config('ROSS_REQUIRE_NEWS'),
            'write_guards_verified': True, 'sdk_attempt_audit_verified': True, 'PAPER_READY': False})
elif phase == 'observe':
    install_console_protection()
    raise SystemExit(supervisor.main(['--seconds','180','--output',str(evidence/'terminal'),'--expected-commit',expected]))
elif phase == 'package':
    # This phase performs filesystem/process checks only. Broker audit belongs
    # exclusively to the existing supervisor after its observed runtime exits.
    evidence.mkdir(exist_ok=True)
    with capture_console(evidence/'packaging'):
        after = source_manifest()
        before_path = evidence/'source-before.json'
        actual_head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
        clean = not subprocess.check_output(['git','status','--porcelain'], cwd=repo, text=True).strip()
        unchanged = (actual_head == expected and clean and before_path.exists()
                     and json.loads(before_path.read_text()) == after)
        write_json(evidence/'source-after.json', after)
        inventory = supervisor.runtime_inventory()
        write_json(evidence/'independent-final-runtime-inventory.json', inventory)
        mutation_ok = False; blockers = []
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
        write_json(evidence/'independent-mutation-validation.json', {'passed': mutation_ok,
            'authority': 'runtime SDK pre-guard counters AND separate supervisor audit counters',
            'not_inferred_from_zero_open_orders': True})
        saved = root/'operator-state-source.json'
        operator_unchanged = False
        if saved.exists():
            original = json.loads(saved.read_text())
            operator_unchanged = digest(Path(original['path'])) == original['sha256']
        for name in ('news.json', 'float.json'):
            path = state/name
            if path.is_file():
                write_json(evidence/'cache-exports'/name, json.loads(path.read_text()))
        terminal_ok = mutation_ok and not blockers and unchanged and operator_unchanged and inventory['completed'] and not inventory['runtimes']
        write_json(evidence/'operator-summary.json', {'head': expected, 'graceful_shutdown': terminal_ok, 'terminal_checks_passed': terminal_ok,
            'tracked_source_unchanged': unchanged, 'operator_order_state_unchanged': operator_unchanged,
            'blockers': blockers, 'scanner_pass': 'REQUIRES_LOG_REVIEW', 'natural_issuer_acquisition': 'REQUIRES_LOG_REVIEW',
            'catalyst': 'REQUIRES_LOG_REVIEW', 'downstream_progression': 'REQUIRES_LOG_REVIEW', 'PAPER_READY': False})
    privacy = scan_artifacts(evidence)
    write_json(evidence/'shareable-evidence-scan.json', privacy)
    if not privacy['passed']:
        raise SystemExit('Privacy scan failed; evidence retained locally, no shareable ZIP.')
    archive = root/'ross-natural-readonly-upload.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as out:
        for path in sorted(evidence.rglob('*')):
            if path.is_file(): out.write(path, path.relative_to(evidence))
    print('SHARE ZIP: '+str(archive))
    raise SystemExit(0 if terminal_ok else 2)
else:
    raise SystemExit('Unknown operator phase')