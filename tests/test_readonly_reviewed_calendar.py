"""Owned READ_ONLY calendar admission only; no observer/provider/broker launch."""
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_readonly_observation_duration import functions, save, OWNER, REPO
from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import build_safe_readonly_env, assert_safe_runtime_env
from src.config.config_registry import CONFIG_REGISTRY
from src.config import config_resolver as cfg

EVIDENCE = 'docs/ross/PR1226_OFFICIAL_CALENDAR_REVIEW_20261114.json'
BASE = '5e961f8b054ea4855393182026353840ff942245'


@pytest.fixture
def owned(tmp_path):
    ns = functions(tmp_path)
    bundle = json.loads((REPO/EVIDENCE).read_bytes())
    manifest = json.loads(bundle['files']['source_manifest.json']['utf8'])
    for name in (*manifest['blobs'], EVIDENCE):
        target = ns['repo']/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    subprocess.run(['git','-C',str(ns['repo']),'add','.'],check=True)
    subprocess.run(['git','-C',str(ns['repo']),'-c','user.name=Fixture','-c','user.email=x@example.invalid','commit','-qm','reviewed owners'],check=True)
    ns['expected'] = subprocess.check_output(['git','-C',str(ns['repo']),'rev-parse','HEAD'],text=True).strip()
    ns.update(CONFIG_REGISTRY=CONFIG_REGISTRY,build_safe_readonly_env=build_safe_readonly_env,
              assert_safe_runtime_env=assert_safe_runtime_env,reviewed_calendar=False)
    return ns


def scrub(ns, enabled):
    """Execute the actual maintained environment block, not a replacement seam."""
    ns['reviewed_calendar'] = enabled
    nodes = ast.parse(OWNER.read_text()).body
    start = next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and ast.unparse(n)=='env = dict(os.environ)')
    end = next(i for i,n in enumerate(nodes) if isinstance(n,ast.Expr) and ast.unparse(n)=='os.environ.update(env)')
    exec(compile(ast.Module(body=nodes[start:end+1],type_ignores=[]),str(OWNER),'exec'),ns)
    return ns['env']


@pytest.mark.parametrize('enabled',[False,True])
def test_actual_scrubbing_and_effective_child_configuration(owned, enabled, monkeypatch):
    ns = owned
    before = dict(os.environ); old_overrides = dict(cfg._CONFIG_OVERRIDES)
    try:
        os.environ.update(ROSS_NEXT_SESSION_CATALYST_ENABLED='true', MARKET_SESSION_COVERAGE='unreviewed',
                          MARKET_HOLIDAYS='2026-11-16', MARKET_HALF_DAYS='2026-11-17', MARKET_EARLY_CLOSE_TIME='12:00',
                          FORCE_SESSION='RTH_OPEN', SESSION_PHASE_OVERRIDE='RTH_OPEN')
        env = scrub(ns,enabled)
        assert env['IBKR_CLIENT_ID']=='71' and env['IBKR_HOST']=='127.0.0.1' and env['IBKR_PORT']=='7497'
        assert env['IBKR_ORDER_SUBMISSION_ENABLED']=='false' and env['IBKR_API_WRITE_ALLOWED']=='false'
        assert 'FORCE_SESSION' not in env and 'SESSION_PHASE_OVERRIDE' not in env
        cfg.set_config_overrides({})
        assert cfg.get_config('ROSS_NEXT_SESSION_CATALYST_ENABLED') is enabled
        if enabled:
            reviewed = json.loads((REPO/EVIDENCE).read_bytes())
            assert cfg.get_config('MARKET_SESSION_COVERAGE')==reviewed['files']['calendar_receipt.json']['utf8'].strip()
            assert {str(x) for x in cfg.get_config('MARKET_HOLIDAYS')}=={'2026-11-26'}
            assert {str(x) for x in cfg.get_config('MARKET_HALF_DAYS')}=={'2026-11-27'}
            assert cfg.get_config('MARKET_EARLY_CLOSE_TIME').isoformat()=='13:00:00'
            binding = ns['binding']()
            assert binding['calendar_enrollment']['enabled'] and binding['head']==ns['expected']
            # Existing supervisor child-environment owner preserves the admitted values/guards.
            child = build_safe_readonly_env(env)
            assert_safe_runtime_env(child)
            for key in ('MARKET_SESSION_COVERAGE','MARKET_HOLIDAYS','MARKET_HALF_DAYS','MARKET_EARLY_CLOSE_TIME','ROSS_NEXT_SESSION_CATALYST_ENABLED'):
                assert child[key]==env[key]
        else:
            assert cfg.get_config('MARKET_SESSION_COVERAGE')==''
            assert ns['binding']()['calendar_enrollment']=={'enabled':False}
    finally:
        os.environ.clear(); os.environ.update(before); cfg.set_config_overrides(old_overrides)


@pytest.mark.parametrize('change',['receipt','owner','source','client','mode','submission'])
def test_explicit_admission_rejects_unbound_inputs(owned, change):
    ns=owned; env=build_safe_readonly_env(dict(IBKR_CLIENT_ID='71',IBKR_HOST='127.0.0.1',IBKR_PORT='7497'))
    if change=='receipt': (ns['repo']/EVIDENCE).write_bytes(b'{}')
    if change=='owner':
        target=ns['repo']/'src/core/time/calendar_session.py'; target.write_text('# changed')
        subprocess.run(['git','-C',str(ns['repo']),'add','.'],check=True)
        subprocess.run(['git','-C',str(ns['repo']),'-c','user.name=Fixture','-c','user.email=x@example.invalid','commit','-qm','changed owner'],check=True)
        ns['expected']=subprocess.check_output(['git','-C',str(ns['repo']),'rev-parse','HEAD'],text=True).strip()
    if change=='source': ns['expected']='0'*40
    if change=='client': env['IBKR_CLIENT_ID']='72'
    if change=='mode': env['RUN_MODE']='PAPER'
    if change=='submission': env['IBKR_ORDER_SUBMISSION_ENABLED']='true'
    with pytest.raises((SystemExit, RuntimeError)):
        ns['reviewed_calendar_environment'](ns['repo'],True,env,ns['expected'])


@pytest.mark.parametrize('initial_eol',['lf','crlf'])
def test_checkout_crlf_is_exact_reviewed_text_not_arbitrary_reencoding(owned,initial_eol):
    ns=owned; path=ns['repo']/EVIDENCE
    env=build_safe_readonly_env(dict(IBKR_CLIENT_ID='71',IBKR_HOST='127.0.0.1',IBKR_PORT='7497'))
    canonical=path.read_bytes().replace(b'\r\n',b'\n')
    path.write_bytes(canonical if initial_eol=='lf' else canonical.replace(b'\n',b'\r\n'))
    initial=ns['reviewed_calendar_environment'](ns['repo'],True,env,ns['expected'])
    path.write_bytes(canonical)
    first=ns['reviewed_calendar_environment'](ns['repo'],True,env,ns['expected'])
    path.write_bytes(canonical.replace(b'\n',b'\r\n'))
    second=ns['reviewed_calendar_environment'](ns['repo'],True,env,ns['expected'])
    assert initial[0]==first[0]
    assert first[0]==second[0] and first[1]['evidence_sha256']==second[1]['evidence_sha256']
    assert first[1]['checkout_bytes_sha256']!=second[1]['checkout_bytes_sha256']
    path.write_bytes(b'\xef\xbb\xbf'+path.read_bytes())
    with pytest.raises(SystemExit):ns['reviewed_calendar_environment'](ns['repo'],True,env,ns['expected'])


@pytest.mark.parametrize('change',['optout','coverage','holiday','halfday','close','receipt'])
def test_prepared_enrollment_is_immutable_across_phases(owned, change):
    ns=owned; before=dict(os.environ); overrides=dict(cfg._CONFIG_OVERRIDES)
    try:
        scrub(ns,True); cfg.set_config_overrides({}); save(ns)
        if change=='optout': ns['reviewed_calendar']=False
        elif change=='receipt': (ns['repo']/EVIDENCE).write_bytes(b'{}')
        else: os.environ[{'coverage':'MARKET_SESSION_COVERAGE','holiday':'MARKET_HOLIDAYS','halfday':'MARKET_HALF_DAYS','close':'MARKET_EARLY_CLOSE_TIME'}[change]]='changed'
        with pytest.raises(SystemExit):ns['require_prepared']()
    finally:
        os.environ.clear(); os.environ.update(before); cfg.set_config_overrides(overrides)


@pytest.mark.parametrize('instant,allowed',[
    ('2026-11-16T14:30:00+00:00',True),
    ('2026-11-16T15:08:59+00:00',True),
    ('2026-11-16T15:09:00+00:00',False),  # E equality is outside opening window.
    ('2026-11-16T14:29:59+00:00',False),  # No new PRE observer authority.
    ('2026-11-16T15:30:00+00:00',False),
    ('2026-11-13T14:30:00+00:00',False),  # Anchor has no reviewed prior slice.
    ('2026-11-14T14:30:00+00:00',False),
    ('2026-11-26T14:30:00+00:00',False),
    ('2026-11-27T14:30:00+00:00',True),
    ('2026-11-30T14:30:00+00:00',True),
    ('2026-12-01T14:30:00+00:00',False),
])
def test_actual_session_owner_bounds_optin_before_runtime(owned, instant, allowed):
    ns=owned; before=dict(os.environ); overrides=dict(cfg._CONFIG_OVERRIDES)
    try:
        scrub(ns,True); cfg.set_config_overrides({})
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None): return datetime.fromisoformat(instant)
        ns['datetime']=Clock
        if allowed: ns['session_check']()
        else:
            with pytest.raises(SystemExit):ns['session_check']()
    finally:
        os.environ.clear(); os.environ.update(before); cfg.set_config_overrides(overrides)


@pytest.mark.parametrize('args,seconds,enrolled',[
    ([],180,False),(['900'],900,False),(['--reviewed-calendar'],180,True),
    (['900','--reviewed-calendar'],900,True),
    (['900','--reviewed-calendar','--premarket'],900,True),
])
def test_actual_argument_admission_preserves_duration_default(args,seconds,enrolled,monkeypatch):
    import sys
    monkeypatch.setattr(sys,'argv',['operator','prepare','unused','a'*40,*args])
    nodes=ast.parse(OWNER.read_text()).body
    stop=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='root' for x in n.targets))
    ns={}; exec(compile(ast.Module(body=nodes[:stop],type_ignores=[]),str(OWNER),'exec'),ns)
    assert ns['runtime_seconds']==seconds and ns['reviewed_calendar'] is enrolled
    assert ns['premarket'] == ('--premarket' in args)


@pytest.mark.parametrize('override', [
    ('FORCE_SESSION', 'RTH_OPEN'), ('READONLY_BENCHMARK_CAPTURE', 'BENCHMARK_CAPTURE_V1'),
])
def test_premarket_rejects_conflicting_inherited_enrollment(override, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['operator', 'prepare', 'unused', 'a'*40,
                                    '900', '--reviewed-calendar', '--premarket'])
    monkeypatch.setenv(*override)
    nodes = ast.parse(OWNER.read_text()).body
    stop = next(i for i, n in enumerate(nodes) if isinstance(n, ast.Assign)
                and any(isinstance(x, ast.Name) and x.id == 'root' for x in n.targets))
    with pytest.raises(SystemExit, match='inherited session or benchmark override'):
        exec(compile(ast.Module(body=nodes[:stop], type_ignores=[]), str(OWNER), 'exec'), {})


@pytest.mark.parametrize('args',[['900','--reviewed-calendar','--reviewed-calendar'],['--reviewed-calendar','900'],['179','--reviewed-calendar'],['1801','--reviewed-calendar'],
    ['900','--premarket'], ['901','--reviewed-calendar','--premarket'],
    ['180','--reviewed-calendar','--premarket','--benchmark-capture'],
    ['900','--reviewed-calendar','--premarket','--premarket'],
    ['900','--reviewed-calendar','--premarket','--rth-open'],
    ['900','--reviewed-calendar','--ordinary-rth'], ['180','--ordinary-rth']])
def test_malformed_optin_arguments_refuse_before_any_phase(args,monkeypatch):
    import sys
    monkeypatch.setattr(sys,'argv',['operator','prepare','unused','a'*40,*args])
    nodes=ast.parse(OWNER.read_text()).body
    stop=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='root' for x in n.targets))
    with pytest.raises((SystemExit,ValueError)):
        exec(compile(ast.Module(body=nodes[:stop],type_ignores=[]),str(OWNER),'exec'),{})


@pytest.mark.parametrize('enabled',[False,True])
def test_effective_owned_child_interpreter_resolves_scoped_config_only(owned,enabled):
    import sys
    ns=owned; before=dict(os.environ)
    try:
        env=dict(scrub(ns,enabled),GIT_SHA=ns['expected'])
    finally:
        os.environ.clear(); os.environ.update(before)
    code='''import json,sys
sys.path.insert(0,sys.argv[1])
def audit(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
        raise AssertionError('Child configuration proof forbids network/children')
sys.addaudithook(audit)
from src.config.config_resolver import get_config
from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import assert_safe_runtime_env
import os
assert_safe_runtime_env(os.environ)
assert 'src.main' not in sys.modules
print('BOUND_CHILD='+json.dumps(dict(python=sys.executable,mode=get_config('RUN_MODE'),
    client=get_config('IBKR_CLIENT_ID'),enabled=get_config('ROSS_NEXT_SESSION_CATALYST_ENABLED'),
    coverage=get_config('MARKET_SESSION_COVERAGE'))))
'''
    result=subprocess.run([sys.executable,'-E','-c',code,str(REPO)],env=env,cwd=ns['repo'],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    payload=json.loads(next(line[len('BOUND_CHILD='):] for line in result.stdout.splitlines() if line.startswith('BOUND_CHILD=')))
    assert Path(payload['python']).resolve()==Path(sys.executable).resolve()
    assert payload['mode']=='READ_ONLY' and payload['client']==71 and payload['enabled'] is enabled
    assert bool(payload['coverage']) is enabled

@pytest.mark.parametrize('instant,allowed', [
    ('2026-11-18T08:59:59+00:00', False),
    ('2026-11-18T09:00:00+00:00', True),
    ('2026-11-18T14:08:59.999999+00:00', True),
    ('2026-11-18T14:09:00+00:00', False),
    ('2026-11-18T14:30:00+00:00', False),
    ('2026-11-26T11:00:00+00:00', False),
    ('2026-11-27T11:00:00+00:00', True),
    ('2026-11-30T09:00:00+00:00', True),
    ('2026-12-01T09:00:00+00:00', False),
])
def test_actual_premarket_admission_requires_full_reviewed_pre_envelope(owned, instant, allowed):
    before = dict(os.environ); overrides = dict(cfg._CONFIG_OVERRIDES)
    now = datetime.fromisoformat(instant)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    try:
        scrub(owned, True)
        cfg.set_config_overrides({})
        owned.update(premarket=True, datetime=Clock, supervisor=supervisor)
        assert owned['binding']()['calendar_enrollment']['phase'] == 'PRE'
        if not allowed:
            with pytest.raises(SystemExit, match='reviewed PRE window'):
                owned['session_check']()
            return
        result = owned['session_check']()
        assert result['phase'] == 'PRE' and result['target_session'] == instant[:10]
        assert result['rth_open'].startswith(instant[:10] + 'T14:30')
        assert result['fingerprint']
    finally:
        os.environ.clear(); os.environ.update(before); cfg.set_config_overrides(overrides)


def test_equal_fingerprints_cannot_admit_a_premarket_envelope_crossing_open(owned):
    from src.market_data.session_pct_change import covered_opening_window

    before = dict(os.environ); overrides = dict(cfg._CONFIG_OVERRIDES)
    try:
        scrub(owned, True)
        cfg.set_config_overrides({})
        now = datetime(2026, 11, 18, 14, 9, tzinfo=timezone.utc)
        start, end = covered_opening_window(now), covered_opening_window(now + timedelta(seconds=1260))
        assert start.fingerprint == end.fingerprint
        assert (start.phase, end.phase) == ('PRE', 'RTH_OPEN')
        with pytest.raises(SystemExit, match='reviewed PRE window'):
            supervisor.require_premarket_window(now, 900)
    finally:
        os.environ.clear(); os.environ.update(before); cfg.set_config_overrides(overrides)


@pytest.mark.parametrize('case', ['valid', 'wrong_identity', 'late_at_spawn', 'conflict'])
def test_supervisor_checks_premarket_at_spawn_without_invoking_runtime(tmp_path, monkeypatch, case):
    from src.market_data import session_pct_change

    now = datetime(2026, 11, 18, 14, 8, 59, tzinfo=timezone.utc)
    checks = iter([now, now + timedelta(seconds=case == 'late_at_spawn')])
    opening = now.replace(minute=30, second=0)
    from types import SimpleNamespace

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(checks)

    for key, value in {'IBKR_HOST':'127.0.0.1', 'IBKR_PORT':'7497', 'IBKR_CLIENT_ID':'71'}.items():
        monkeypatch.setenv(key,value)
    monkeypatch.setattr(supervisor, 'datetime', Clock)
    monkeypatch.setattr(supervisor, 'install_console_protection', lambda: None)
    monkeypatch.setattr(supervisor, 'require_clean_certification_worktree', lambda _: None)
    monkeypatch.setattr(session_pct_change, 'covered_opening_window', lambda point: SimpleNamespace(
        phase='PRE' if point < opening else 'RTH_OPEN', target_session='2026-11-18',
        fingerprint='reviewed', current_open=opening))
    window = supervisor.require_premarket_window(now, 900)
    if case == 'wrong_identity':
        window['target_session'] = '2026-11-17'

    reached = []
    class LaunchIntercepted(Exception):
        pass
    def intercept(command, **kwargs):
        from src.runtime.process_identity import FULL_CORE_CLIENT71, HANDSHAKE_NONCE
        assert kwargs['env'][FULL_CORE_CLIENT71] == kwargs['env'][HANDSHAKE_NONCE]
        assert kwargs['env']['PR1090_PREMARKET_HISTORY_EVIDENCE'] == '1'
        reached.append(command)
        raise LaunchIntercepted
    monkeypatch.setattr(supervisor.subprocess, 'Popen', intercept)
    output = tmp_path/'terminal'
    args = ['--seconds', '900', '--output', str(output), '--expected-commit', 'a' * 40]
    if case == 'conflict':
        args.append('--benchmark-capture')
    with pytest.raises(LaunchIntercepted if case == 'valid' else SystemExit):
        supervisor.main(args, premarket_window=window, full_core_admitted=True)
    assert reached == ([[sys.executable, '-u', '-m', 'src.main']] if case == 'valid' else [])
    if case == 'valid':
        assert json.loads((output/'premarket-launch.json').read_text())['phase'] == 'PRE'


def test_premarket_history_evidence_projects_existing_dispatch_and_completion(monkeypatch, capsys):
    from src.ibkr.market_data_client import historical_request_spec, record_premarket_history

    arguments = dict(end_date_time='20261118 13:00:00 UTC', duration_str='1200 S',
                     bar_size_setting='1 min', what_to_show='TRADES', use_rth=0,
                     format_date=2, keep_up_to_date=False, chart_options=[])
    request = historical_request_spec(**arguments)
    state = dict(status='COMPLETE_BARS', end_received=True,
                 request_dispatched_at_utc='2026-11-18T13:00:00+00:00',
                 completed_at_utc='2026-11-18T13:00:01+00:00')
    monkeypatch.delenv('PR1090_PREMARKET_HISTORY_EVIDENCE', raising=False)
    record_premarket_history('ibapi', 7, request, state, owned=True, cancellation='NOT_OUTSTANDING')
    assert capsys.readouterr().out == ''
    monkeypatch.setenv('PR1090_PREMARKET_HISTORY_EVIDENCE', '1')
    record_premarket_history('ibapi', 7, request, state, owned=True, cancellation='NOT_OUTSTANDING')
    output = capsys.readouterr().out
    receipt = json.loads(output.split('[IBKR][HISTORICAL_PRE_EVIDENCE] ', 1)[1])
    assert receipt['request_id'] == 7 and receipt['request_spec']['use_rth'] == 0
    assert receipt['request_spec']['end_date_time'] == arguments['end_date_time']
    assert receipt['end_received'] and receipt['owned_at_retirement']
    assert receipt['completed_utc'] == state['completed_at_utc']

@pytest.mark.parametrize('instant,allowed', [
    ('2026-11-18T14:29:00+00:00', False),
    ('2026-11-18T18:30:00+00:00', True),
    ('2026-11-18T20:38:59+00:00', True),
    ('2026-11-18T20:39:00+00:00', False),
    ('2026-11-26T16:00:00+00:00', False),
    ('2026-11-27T17:38:59+00:00', True),
    ('2026-11-27T17:39:00+00:00', False),
    ('2026-12-01T16:00:00+00:00', False),
])
def test_ordinary_rth_uses_full_session_close_without_opening_enrollment(owned, instant, allowed):
    before = dict(os.environ); overrides = dict(cfg._CONFIG_OVERRIDES)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(instant)
    try:
        owned.update(ordinary_rth=True, datetime=Clock)
        scrub(owned, False)
        cfg.set_config_overrides({})
        assert not cfg.get_config('ROSS_NEXT_SESSION_CATALYST_ENABLED')
        enrollment = owned['binding']()['calendar_enrollment']
        assert not enrollment['enabled'] and enrollment['phase'] == 'RTH'
        if allowed:
            owned['session_check']()
        else:
            with pytest.raises(SystemExit):
                owned['session_check']()
    finally:
        os.environ.clear(); os.environ.update(before); cfg.set_config_overrides(overrides)
