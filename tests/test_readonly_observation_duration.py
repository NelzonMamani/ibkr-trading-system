"""Guarded serial manifest/admission controls; no runtime or broker operation."""
import ast
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import types

import pytest

REPO = Path(__file__).resolve().parents[1]
OWNER = REPO/'scripts/certification/natural_readonly_operator.py'


def functions(tmp_path):
    root = tmp_path; repo = root/'s'; repo.mkdir()
    (root/'e').mkdir(); (root/'preparation').mkdir(); (root/'state/startup').mkdir(parents=True)
    (repo/'a').write_bytes(b'one!'); (repo/'b').write_bytes(b'other')
    hook = repo/'scripts/certification/readonly_cache_sitecustomize.py'
    hook.parent.mkdir(parents=True); hook.write_text('# hook')
    (root/'state/startup/sitecustomize.py').write_bytes(hook.read_bytes())
    subprocess.run(['git','init','-q',str(repo)],check=True)
    subprocess.run(['git','-C',str(repo),'add','.'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=x@example.invalid','commit','-qm','fixture'],check=True)
    expected = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    ns = dict(root=root,repo=repo,state=root/'state',evidence=root/'e',expected=expected,
              runtime_seconds=900, phase='preflight', hashlib=hashlib, subprocess=subprocess,json=json,
              os=os,sys=sys,Path=Path,time=time,datetime=datetime,timezone=timezone,
              shutil=shutil,CONFIG_REGISTRY={},preflight_timing=lambda _:None)
    tree = ast.parse(OWNER.read_text())
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name != 'preflight_timing':
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(OWNER),'exec'),ns)
    return ns


def save(ns):
    root=ns['root']; prepared={'binding':ns['binding']()}
    (root/'preparation/prepared.json').write_text(json.dumps(prepared))
    (root/'preparation/prepare-process.process.json').write_text(json.dumps(dict(exited=True,timely_exit_verified=True,exit_code=0)))
    return prepared


def test_serial_equivalence_and_content_edit_despite_same_metadata(tmp_path):
    ns=functions(tmp_path); manifest=ns['complete_manifest']()
    assert manifest == {name:hashlib.sha256((ns['repo']/name).read_bytes()).hexdigest() for name in manifest}
    a=ns['repo']/'a'; before=a.stat(); a.write_bytes(b'two!'); os.utime(a,ns=(before.st_atime_ns,before.st_mtime_ns))
    assert ns['complete_manifest']()!=manifest
    a.unlink()
    assert ns['source_manifest']()['a'] is None
    with pytest.raises(SystemExit):ns['complete_manifest']()


def test_read_failure_propagates(tmp_path,monkeypatch):
    ns=functions(tmp_path); real=Path.read_bytes
    def deny(path):
        if path.name=='a': raise PermissionError('controlled')
        return real(path)
    monkeypatch.setattr(Path,'read_bytes',deny)
    with pytest.raises(PermissionError):ns['complete_manifest']()


@pytest.mark.parametrize('field',['root','head','tree','seconds','config','hook','hook_source','python'])
def test_preparation_bindings_fail_closed(tmp_path,field):
    ns=functions(tmp_path); prepared=save(ns)
    prepared['binding'][field]='changed'
    (tmp_path/'preparation/prepared.json').write_text(json.dumps(prepared))
    with pytest.raises(SystemExit):ns['require_prepared']()


@pytest.mark.parametrize('field,value',[('exited',False),('timely_exit_verified',False),('exit_code',1)])
def test_late_or_unknown_preparation_never_admits(tmp_path,field,value):
    ns=functions(tmp_path);save(ns)
    receipt=dict(exited=True,timely_exit_verified=True,exit_code=0);receipt[field]=value
    (tmp_path/'preparation/prepare-process.process.json').write_text(json.dumps(receipt))
    with pytest.raises(SystemExit):ns['require_prepared']()


def observe_block():
    node=next(n for n in ast.walk(ast.parse(OWNER.read_text())) if isinstance(n,ast.If) and ast.unparse(n.test)=="phase == 'observe'")
    return compile(ast.Module(body=node.body,type_ignores=[]),str(OWNER),'exec')


@pytest.mark.parametrize('case',['valid','stale','reused','parent','operator','hook','late','session','interrupted'])
def test_real_observe_entry_only_dispatches_after_single_use_admission(tmp_path,monkeypatch,case):
    ns=functions(tmp_path);save(ns)
    controller={'pid':os.getppid(),'token':'fixture'}
    if os.name == 'nt':
        from src.runtime.process_identity import WindowsProcessHandle
        handle = WindowsProcessHandle(controller['pid'])
        try: controller['creation_token'] = handle.creation_token
        finally: handle.close()
    (tmp_path/'runner.json').write_text(json.dumps(controller));monkeypatch.setenv('READONLY_ADMISSION_TOKEN','fixture')
    original=tmp_path/'original';original.write_bytes(b'state')
    (tmp_path/'operator-state-source.json').write_text(json.dumps({'path':str(original),'sha256':ns['digest'](original)}))
    admission={'binding':ns['binding'](),'controller':controller,'operator_receipt':ns['digest'](tmp_path/'operator-state-source.json'),
               'issued_monotonic':time.monotonic()-(30 if case=='stale' else 0),'issued_utc':time.time()}
    (tmp_path/'admission.json').write_text(json.dumps(admission))
    (tmp_path/'e/preflight-process.process.json').write_text(json.dumps(dict(exited=True,timely_exit_verified=case!='late',exit_code=0)))
    (tmp_path/'e/preflight-result.json').write_text('{"status":"PASS"}')
    (tmp_path/'e/preflight.json').write_text(json.dumps(dict(seconds=900,head=ns['expected'])))
    if case=='interrupted':(tmp_path/'e/preflight.stop').touch()
    if case=='operator':original.write_bytes(b'changed')
    if case=='hook':(tmp_path/'state/startup/sitecustomize.py').write_text('changed')
    if case=='parent':monkeypatch.setenv('READONLY_ADMISSION_TOKEN','wrong')
    if case=='reused':(tmp_path/'admission-consumed').touch()
    called=[]
    def dispatch(args):called.append(args);return 0
    def session():
        if case=='session':raise SystemExit('closed')
    ns.update(supervisor=types.SimpleNamespace(require_clean_certification_worktree=lambda _:None,main=dispatch),
              session_check=session,install_console_protection=lambda:None,
              write_json=lambda path,value:path.write_text(json.dumps(value)))
    with pytest.raises((SystemExit,FileExistsError)) as result:exec(observe_block(),ns)
    assert bool(called)==(case=='valid')
    if case=='valid':assert result.value.code==0 and (tmp_path/'admission-consumed').exists()


def test_session_requires_entire_supervisor_window(tmp_path,monkeypatch):
    ns=functions(tmp_path)
    from src.config import system_config
    seen=[]
    def session(now):seen.append(now);return 'RTH' if len(seen)==1 else 'AH'
    monkeypatch.setattr(system_config,'get_current_market_session',session)
    with pytest.raises(SystemExit):ns['session_check']()
    assert (seen[1]-seen[0]).total_seconds()==1260


def test_stop_prevents_partial_manifest(tmp_path):
    ns=functions(tmp_path)
    (tmp_path/'e/preflight.stop').touch()
    with pytest.raises(SystemExit):ns['complete_manifest']()


def test_calendar_binding_is_hash_seed_independent(tmp_path):
    code = """import ast,json,sys
from datetime import date,time
source=ast.parse(open(sys.argv[1]).read())
node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='canonical_config')
exec(compile(ast.Module(body=[node],type_ignores=[]),'<owner>','exec'))
print(json.dumps(canonical_config({'dates':{date(2026,12,25),date(2026,11,26)},'times':{'09:30','16:00'}}),sort_keys=True))
"""
    results = [subprocess.check_output([sys.executable,'-c',code,str(OWNER)],env=dict(os.environ,PYTHONHASHSEED=str(seed)),text=True) for seed in (1,2,3)]
    assert len(set(results))==1

@pytest.mark.parametrize('case',['valid','content-edit','missing','session-expired','inventory','cache-unowned','hook-change'])
def test_entire_final_preflight_body_requires_fresh_manifest_and_final_guards(tmp_path,monkeypatch,case):
    for key in ('NEWS_ENABLED','NEWS_MAINTENANCE_ENABLED','ROSS_ISSUER_QUERY_ENABLED'):
        monkeypatch.setenv(key,'true')
    ns=functions(tmp_path);save(ns)
    m0=ns['complete_manifest']();(tmp_path/'preparation/source-prepared.json').write_text(json.dumps(m0))
    original=tmp_path/'original';original.write_bytes(b'operator')
    if case=='content-edit':
        a=ns['repo']/'a';stat=a.stat();a.write_bytes(b'two!');os.utime(a,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    if case=='missing':(ns['repo']/'a').unlink()
    from scripts.certification import readonly_cache_probe
    def probe(*args):
        if case=='cache-unowned':raise RuntimeError('controlled cleanup unavailable')
        if case=='hook-change':(tmp_path/'state/startup/sitecustomize.py').write_text('different')
    monkeypatch.setattr(readonly_cache_probe,'run_cache_probe',probe)
    sessions=[]; guards=[]; inventories=[]
    def session():
        sessions.append(True)
        if case=='session-expired' and len(sessions)==2:raise SystemExit('session expired during hashing')
    def inventory():
        inventories.append(True)
        return {'completed':not(case=='inventory' and len(inventories)==2),'runtimes':[]}
    def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    ns.update(os=types.SimpleNamespace(name='nt'),sys=types.SimpleNamespace(version_info=(3,13,3),executable=sys.executable),
        require_controller=lambda:{'pid':1,'token':'fixture'},require_prepared=lambda:json.loads((tmp_path/'preparation/prepared.json').read_text()),
        session_check=session,verify_write_guards=lambda:guards.append(True),
        supervisor=types.SimpleNamespace(require_clean_certification_worktree=lambda _:None,runtime_inventory=inventory),
        write_json=write,capture_console=lambda _:nullcontext(),env={},original_state=original)
    node=next(n for n in ast.walk(ast.parse(OWNER.read_text())) if isinstance(n,ast.If) and ast.unparse(n.test)=="phase == 'preflight'")
    if case=='valid':exec(compile(ast.Module(body=node.body,type_ignores=[]),str(OWNER),'exec'),ns)
    else:
        with pytest.raises((SystemExit,RuntimeError)):exec(compile(ast.Module(body=node.body,type_ignores=[]),str(OWNER),'exec'),ns)
    assert (tmp_path/'admission.json').exists()==(case=='valid')
    assert json.loads((tmp_path/'preparation/source-prepared.json').read_text())==m0
    if case=='valid':
        assert len(sessions)==2 and len(guards)==2 and len(inventories)==2
        assert json.loads((tmp_path/'e/source-before.json').read_text())==m0
        assert (tmp_path/'state/order-id.json').read_bytes()==b'operator'


def test_actual_wrong_source_pin_rejected(tmp_path):
    ns=functions(tmp_path);ns['expected']='a'*40
    with pytest.raises(SystemExit):ns['binding']()


def test_actual_prepare_body_is_filesystem_only_and_captures_full_m0(tmp_path):
    ns=functions(tmp_path)
    shutil.rmtree(tmp_path/'e');shutil.rmtree(tmp_path/'state')
    def forbidden(*args,**kwargs):raise AssertionError('Session/operator/broker admission forbidden in preparation')
    writes=[]
    def write(path,value):writes.append(path.name);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    ns.update(phase='prepare',os=types.SimpleNamespace(name='nt'),
        sys=types.SimpleNamespace(version_info=(3,13,3),executable=sys.executable),
        supervisor=types.SimpleNamespace(require_clean_certification_worktree=lambda _:None),
        session_check=forbidden,require_controller=forbidden,write_json=write)
    node=next(n for n in ast.walk(ast.parse(OWNER.read_text())) if isinstance(n,ast.If) and ast.unparse(n.test)=="phase == 'prepare'")
    exec(compile(ast.Module(body=node.body,type_ignores=[]),str(OWNER),'exec'),ns)
    m0=json.loads((tmp_path/'preparation/source-prepared.json').read_text())
    assert m0==ns['complete_manifest']()
    assert not (tmp_path/'e').exists() and not (tmp_path/'operator-state-source.json').exists()
    assert not (tmp_path/'state/order-id.json').exists()
    assert writes==['source-prepared.json','prepared.json']
