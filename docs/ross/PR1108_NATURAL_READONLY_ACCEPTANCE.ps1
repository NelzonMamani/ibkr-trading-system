# REVIEW COPY. No launch is authorized by preparation of this command.
& {
    $ErrorActionPreference = 'Stop'
    $PSNativeCommandUseErrorActionPreference = $false
    $WorkstationAccepted = $false
    $ObservationAuthorized = $false
    # Keep both false until the workstation result and the two material findings
    # have an explicit disposition. A repaired head needs a newly pinned package.
    if (!$WorkstationAccepted -or !$ObservationAuthorized) {
        throw 'HOLD: workstation acceptance and explicit observation authorization are pending; see checkpoint findings.'
    }
    $obsHead = '8f40e4c4b3ca8fa0f74d8e41cd947e50bc2e370c'
    $obsPython = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $obsPython -PathType Leaf)) { throw "Missing $obsPython" }
    $obsSource = (& git rev-parse --show-toplevel | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or !$obsSource) { throw 'Run from your existing PyCharm repository.' }
    $obsOrigin = (& git -C $obsSource remote get-url origin | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $obsOrigin -notmatch '(?i)github\.com[:/]NelzonMamani/ibkr-trading-system(?:\.git)?/?$') { throw 'Unexpected source repository.' }
    $obsRoot = 'C:\tmp\ro1108-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    New-Item -ItemType Directory -Path $obsRoot | Out-Null
    $obsCheckout = Join-Path $obsRoot 's'
    $obsEvidence = Join-Path $obsRoot 'e'
    $obsHelper = Join-Path $obsRoot 'operator.py'
    & git clone --no-checkout --no-hardlinks -- $obsSource $obsCheckout
    if ($LASTEXITCODE -ne 0) { throw 'Isolated clone failed.' }
    & git -C $obsCheckout config --local core.longpaths true
    if ($LASTEXITCODE -ne 0) { throw 'Long-path setup failed.' }
    & git -C $obsCheckout remote set-url origin https://github.com/NelzonMamani/ibkr-trading-system.git
    if ($LASTEXITCODE -ne 0) { throw 'Origin setup failed.' }
    & git -C $obsCheckout fetch --no-tags origin refs/heads/codex/natural-readonly-enrichment-stop
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
    $obsFetched = (& git -C $obsCheckout rev-parse FETCH_HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $obsFetched -cne $obsHead) { throw 'Branch differs from the reviewed head; obtain a new package.' }
    & git -C $obsCheckout checkout --detach $obsHead
    if ($LASTEXITCODE -ne 0) { throw 'Reviewed checkout failed.' }
    @'
import hashlib, json, os, shutil, subprocess, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
phase, root_text, expected = sys.argv[1:]
root = Path(root_text); repo = root/'s'; evidence = root/'e'; state = root/'state'
sys.path.insert(0, str(repo)); os.chdir(repo)
if hasattr(sys.modules.get('sitecustomize'), 'offline'):
    raise SystemExit('Offline pytest hook present: observation must use a separate process.')
from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import build_safe_readonly_env, assert_safe_runtime_env
from src.config.config_registry import CONFIG_REGISTRY
env = dict(os.environ)
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
    evidence.mkdir(); state.mkdir()
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
        hook.write_text("import os\ntry:\n import yfinance.cache as c\n c.set_cache_location(os.environ['PR1108_YFINANCE_CACHE'])\nexcept BaseException:\n os._exit(78)\n", encoding='utf-8')
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
        unchanged = before_path.exists() and json.loads(before_path.read_text()) == after
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
        write_json(evidence/'operator-summary.json', {'head': expected, 'terminal_checks_passed': terminal_ok,
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
'@ | Set-Content -LiteralPath $obsHelper -Encoding UTF8
    $obsResult = 1
    try {
        & $obsPython -E -u $obsHelper preflight $obsRoot $obsHead
        if ($LASTEXITCODE -ne 0) { throw "Preflight failed; inspect $obsEvidence\preflight" }
        Write-Host "Logs: $obsEvidence\terminal\stdout.log and stderr.log"
        Write-Host "Early stop: create $obsEvidence\terminal\STOP_REQUESTED (do not terminate Python)."
        $obsProcess = Start-Process -FilePath $obsPython -ArgumentList @('-E','-u',$obsHelper,'observe',$obsRoot,$obsHead) -WorkingDirectory $obsCheckout -RedirectStandardOutput (Join-Path $obsEvidence 'supervisor.stdout.log') -RedirectStandardError (Join-Path $obsEvidence 'supervisor.stderr.log') -PassThru
        $obsClock = [Diagnostics.Stopwatch]::StartNew()
        while (!$obsProcess.WaitForExit(5000)) {
            $obsLog = Join-Path $obsEvidence 'terminal\stdout.log'
            $obsBytes = if (Test-Path $obsLog) { (Get-Item $obsLog).Length } else { 0 }
            Write-Host ("Elapsed {0:N0}s; runtime stdout {1} bytes; evidence {2}" -f $obsClock.Elapsed.TotalSeconds,$obsBytes,$obsEvidence)
            if ((Test-Path $obsLog) -and (Select-String -LiteralPath $obsLog -SimpleMatch '[SCANNER][IBKR][RAW_ZERO]' -Quiet)) {
                'GRACEFUL_STOP_REQUESTED' | Set-Content (Join-Path $obsEvidence 'terminal\STOP_REQUESTED')
                Write-Host 'Broker-zero fallback detected: natural acceptance is invalid; requesting graceful stop.'
            }
            if ($obsClock.Elapsed.TotalSeconds -gt 540) {
                if (Test-Path (Join-Path $obsEvidence 'terminal')) { 'GRACEFUL_STOP_REQUESTED' | Set-Content (Join-Path $obsEvidence 'terminal\STOP_REQUESTED') }
                throw 'Supervisor exceeded outer observation/finalization budget. No success claim or broad process kill; retain evidence and inspect surviving process.'
            }
        }
        $obsProcess.WaitForExit()
        $obsResult = $obsProcess.ExitCode
    } finally {
        & $obsPython -E -u $obsHelper package $obsRoot $obsHead
        $obsPackageResult = $LASTEXITCODE
        Write-Host "Retained checkout: $obsCheckout`nEvidence: $obsEvidence`nSupervisor exit: $obsResult"
    }
    if ($obsResult -ne 0 -or $obsPackageResult -ne 0) { throw 'Observation/terminal verification incomplete or failed; share the retained diagnostic ZIP if privacy scan passed.' }
    Write-Host 'Terminal checks passed. Scanner, issuer, catalyst and downstream outcomes still require separate evidence review. PAPER_READY=NO.'
}
