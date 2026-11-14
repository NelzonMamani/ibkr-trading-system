"""Owned READ_ONLY calendar admission only; no observer/provider/broker launch."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from test_readonly_observation_duration import functions, save, OWNER, REPO
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
])
def test_actual_argument_admission_preserves_duration_default(args,seconds,enrolled,monkeypatch):
    import sys
    monkeypatch.setattr(sys,'argv',['operator','prepare','unused','a'*40,*args])
    nodes=ast.parse(OWNER.read_text()).body
    stop=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='root' for x in n.targets))
    ns={}; exec(compile(ast.Module(body=nodes[:stop],type_ignores=[]),str(OWNER),'exec'),ns)
    assert ns['runtime_seconds']==seconds and ns['reviewed_calendar'] is enrolled


@pytest.mark.parametrize('args',[['900','--reviewed-calendar','--reviewed-calendar'],['--reviewed-calendar','900'],['179','--reviewed-calendar'],['1801','--reviewed-calendar']])
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
