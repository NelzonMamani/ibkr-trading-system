"""Disposable OFFLINE Windows Job Object feasibility. No production imports.

Run directly: python -I -S -B tests/test_manifest_windows_containment_feasibility.py
Only synthetic sleep/IPC/startup controls; no manifest hashing or broker access.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as W
import json
import ast
import hashlib
import shutil
import zlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve()
MAX_MEMBERS = 10  # bounded native members, including observed Python launch processes
# Logical work remains one coordinator + at most four workers; no extra tasks.
INTENDED_BUDGETS = (90, 30)


def offline_guard(event, args):
    if event.startswith('socket.') or event in ('os.system', 'os.fork'):
        raise RuntimeError('Filesystem-only containment control')
    if event == 'import' and str(args[0]).split('.')[0] in {'src', 'ibapi', 'ib_insync', 'requests', 'curl_cffi', 'yfinance'}:
        raise RuntimeError('No operational/provider/broker imports')
    if event == 'subprocess.Popen':
        raise RuntimeError('Use only retained native synthetic child handles')


sys.addaudithook(offline_guard)


class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', W.DWORD), ('lpReserved', W.LPWSTR), ('lpDesktop', W.LPWSTR),
                ('lpTitle', W.LPWSTR), ('dwX', W.DWORD), ('dwY', W.DWORD),
                ('dwXSize', W.DWORD), ('dwYSize', W.DWORD), ('dwXCountChars', W.DWORD),
                ('dwYCountChars', W.DWORD), ('dwFillAttribute', W.DWORD),
                ('dwFlags', W.DWORD), ('wShowWindow', W.WORD), ('cbReserved2', W.WORD),
                ('lpReserved2', ctypes.POINTER(W.BYTE)), ('hStdInput', W.HANDLE),
                ('hStdOutput', W.HANDLE), ('hStdError', W.HANDLE)]


class PROCESSINFO(ctypes.Structure):
    _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE),
                ('dwProcessId', W.DWORD), ('dwThreadId', W.DWORD)]


class LIMITS(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', W.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', W.DWORD),
                ('Affinity', ctypes.c_size_t), ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]


class IOCOUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in ('ReadOperationCount', 'WriteOperationCount',
                'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class EXTENDED(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', LIMITS), ('IoInfo', IOCOUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


class PIDLIST(ctypes.Structure):
    _fields_ = [('assigned', W.DWORD), ('count', W.DWORD), ('pids', ctypes.c_size_t * MAX_MEMBERS)]


class API:
    """Retained native handles, following process_identity's wait/exit pattern."""
    def __init__(self):
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        specs = {
            'CreateJobObjectW': ([ctypes.c_void_p, W.LPCWSTR], W.HANDLE),
            'SetInformationJobObject': ([W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD], W.BOOL),
            'QueryInformationJobObject': ([W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.c_void_p], W.BOOL),
            'AssignProcessToJobObject': ([W.HANDLE, W.HANDLE], W.BOOL),
            'IsProcessInJob': ([W.HANDLE, W.HANDLE, ctypes.POINTER(W.BOOL)], W.BOOL),
            'TerminateJobObject': ([W.HANDLE, W.UINT], W.BOOL),
            'CreateProcessW': ([W.LPCWSTR, W.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, W.BOOL, W.DWORD, ctypes.c_void_p, W.LPCWSTR, ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESSINFO)], W.BOOL),
            'ResumeThread': ([W.HANDLE], W.DWORD),
            'OpenProcess': ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            'QueryFullProcessImageNameW': ([W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)], W.BOOL),
            'WaitForSingleObject': ([W.HANDLE, W.DWORD], W.DWORD),
            'GetExitCodeProcess': ([W.HANDLE, ctypes.POINTER(W.DWORD)], W.BOOL),
            'GetProcessTimes': ([W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4, W.BOOL),
            'TerminateProcess': ([W.HANDLE, W.UINT], W.BOOL),
            'CloseHandle': ([W.HANDLE], W.BOOL),
        }
        for name, (arguments, result) in specs.items():
            fn = getattr(self.k, name); fn.argtypes = arguments; fn.restype = result
        self.handles = set()
        self.fault = None

    def fail(self, operation):
        if self.fault == operation:
            self.fault = None  # one injected denial; recovery never rewrites result
            raise OSError('INJECTED_' + operation)

    def checked(self, result):
        if not result: raise ctypes.WinError(ctypes.get_last_error())
        return result

    def own(self, handle):
        self.checked(handle); self.handles.add(int(handle)); return int(handle)

    def close(self, handle):
        self.fail('close')
        self.checked(self.k.CloseHandle(handle)); self.handles.remove(handle)

    def create_job(self):
        job = self.own(self.k.CreateJobObjectW(None, None))
        limits = EXTENDED()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE, ACTIVE_PROCESS
        limits.BasicLimitInformation.ActiveProcessLimit = MAX_MEMBERS
        self.checked(self.k.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        return job

    def spawn(self, root, role, mode, *, suspended=True, breakaway=False):
        return self.spawn_argv(root,[sys.executable,'-I','-S','-B','-u',str(HERE),'--child',str(root),role,mode],suspended=suspended,breakaway=breakaway)

    def spawn_argv(self, root, argv, *, suspended=True, breakaway=False):
        command = subprocess.list2cmdline(argv)
        startup = STARTUPINFO(); startup.cb = ctypes.sizeof(startup)
        info = PROCESSINFO()
        self.checked(self.k.CreateProcessW(argv[0], ctypes.create_unicode_buffer(command), None, None,
                     False, 0x08000000 | (0x4 if suspended else 0) | (0x01000000 if breakaway else 0), None, str(root), ctypes.byref(startup), ctypes.byref(info)))
        # Registration has no I/O; retain process AND primary thread immediately.
        return {'process': self.own(info.hProcess), 'thread': self.own(info.hThread), 'pid': info.dwProcessId, 'assigned': False}

    def assign(self, job, process):
        self.fail('assign')
        self.checked(self.k.AssignProcessToJobObject(job, process['process']))
        process['assigned'] = True
        if not self.member(job, process['process']): raise RuntimeError('MEMBERSHIP_UNKNOWN')

    def resume(self, process):
        if not process['assigned']: raise RuntimeError('Never resume before assignment')
        if self.k.ResumeThread(process['thread']) == 0xFFFFFFFF: raise ctypes.WinError(ctypes.get_last_error())

    def member(self, job, process):
        present = W.BOOL()
        self.checked(self.k.IsProcessInJob(process, job, ctypes.byref(present)))
        return bool(present.value)

    def members(self, job):
        self.fail('query')
        info = PIDLIST()
        self.checked(self.k.QueryInformationJobObject(job, 3, ctypes.byref(info), ctypes.sizeof(info), None))
        if info.count > MAX_MEMBERS or info.assigned != info.count: raise RuntimeError('MEMBERSHIP_INCOMPLETE')
        return list(info.pids[:info.count])

    def open(self, pid):
        return self.own(self.k.OpenProcess(0x1000 | 0x100000 | 0x1, False, pid))

    def image_kind(self, handle):
        length=W.DWORD(32768); text=ctypes.create_unicode_buffer(length.value)
        self.checked(self.k.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(length)))
        image=Path(text.value)
        return {'image_class':'PYTHON' if image.name.lower() in ('python.exe','python3.exe','pythonw.exe') else 'OTHER', 'same_as_controller_executable':os.path.normcase(str(image))==os.path.normcase(sys.executable)}

    def token(self, handle):
        fields = [W.FILETIME() for _ in range(4)]
        self.checked(self.k.GetProcessTimes(handle, *(ctypes.byref(f) for f in fields)))
        return (fields[0].dwHighDateTime << 32) | fields[0].dwLowDateTime

    def wait(self, handle, deadline):
        self.fail('wait')
        remaining = max(0., deadline-time.monotonic())
        value = self.k.WaitForSingleObject(handle, int(min(remaining*1000, 0xFFFFFFFE)))
        if value == 258: return False
        if value != 0: raise ctypes.WinError(ctypes.get_last_error())
        code = W.DWORD(); self.checked(self.k.GetExitCodeProcess(handle, ctypes.byref(code)))
        return True

    def exit_code(self, handle):
        code = W.DWORD(); self.checked(self.k.GetExitCodeProcess(handle,ctypes.byref(code)))
        return code.value

    def terminate(self, job):
        self.fail('terminate')
        self.checked(self.k.TerminateJobObject(job, 97))


def read_small(path):
    with path.open('rb') as stream: raw = stream.read(4097)
    if len(raw) > 4096: raise RuntimeError('IPC_LIMIT')
    return json.loads(raw)


def child(root, role, mode):
    """Synthetic child script: no hashing, config, providers or operator imports."""
    api = API()
    temporary=root/('role-'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps({'pid':os.getpid(),'role':role,'mode':mode}))
    temporary.replace(root/('role-'+str(os.getpid())+'.json'))
    if role == 'leaf':
        (root/('leaf-' + str(os.getpid()))).write_text('ready')
        while True: time.sleep(.01)  # intentional owned blocked worker
    if role == 'exit-controller':
        job = None; p = None
        try:
            job = api.create_job()
            p = api.spawn(root, 'coordinator', 'descendants')
            if mode == 'assign-fail':
                temporary=root/'unassigned.tmp'
                temporary.write_text(json.dumps({'pid':p['pid'],'creation':api.token(p['process'])}))
                temporary.replace(root/'unassigned')
                while not (root/'continue-assignment').exists(): time.sleep(.005)
                api.fault='assign'
            api.assign(job, p); api.resume(p)
            end = time.monotonic()+10
            while time.monotonic()<end:
                ids=api.members(job)
                roles=[read_small(path) for path in root.glob('role-*.json')]
                members=[r for r in roles if r['pid'] in ids]
                if sum(r['role']=='leaf' for r in members)==2: break
                time.sleep(.005)
            else: raise RuntimeError('LEAF_ROLES_NOT_READY')
            if not 3 <= len(ids) <= MAX_MEMBERS: raise RuntimeError('DESCENDANTS_NOT_READY')
            if sum(r['role']=='coordinator' for r in members)!=1: raise RuntimeError('COORDINATOR_NOT_MEMBER')
            proof = []
            for pid in ids:
                h = api.open(pid)
                if not api.member(job,h): raise RuntimeError('NOT_MEMBER')
                proof.append({'pid':pid, 'creation':api.token(h)})
                api.close(h)
            temporary = root/'controller-ready.tmp'
            temporary.write_text(json.dumps(proof))
            temporary.replace(root/'controller-ready')
            while not (root/'exit-controller').exists(): time.sleep(.005)
            # Deliberately bypass finally: OS handle closure must kill the job.
            os._exit(0)
        finally:
            # Setup/assignment failure MUST retire the suspended child even if
            # it never became a member; kill-on-close alone cannot cover it.
            end = time.monotonic()+3
            if p and not p['assigned']:
                api.checked(api.k.TerminateProcess(p['process'],99))
            if job: api.checked(api.k.TerminateJobObject(job,99))
            if p and not api.wait(p['process'],end): raise RuntimeError('SETUP_PROCESS_LEAK')
            if job:
                while api.members(job):
                    if time.monotonic() >= end: raise RuntimeError('SETUP_JOB_LEAK')
                    time.sleep(.005)
            for h in list(api.handles): api.close(h)
    if role != 'coordinator': raise RuntimeError('ROLE')
    if mode in ('startup', 'ipc'):
        (root/'ready').write_text('1')
        while True: time.sleep(.01)  # controlled startup/IPC wait, not actual OS hang
    if mode in ('descendants', 'partial', 'breakaway'):
        children = []
        if mode == 'breakaway':
            try:
                escaped = api.spawn(root,'leaf','block',suspended=False,breakaway=True)
            except OSError:
                (root/'breakaway-denied').write_text('1')
            else:
                api.checked(api.k.TerminateProcess(escaped['process'],99))
                api.wait(escaped['process'],time.monotonic()+3)
                api.close(escaped['thread']); api.close(escaped['process'])
                raise RuntimeError('BREAKAWAY_UNEXPECTEDLY_ALLOWED')
        for index in range(2):
            if mode == 'partial' and index == 1: break
            # Descendants inherit their parent's job WITHOUT breakaway flags.
            p = api.spawn(root, 'leaf', 'block', suspended=False)
            children.append(p)
            api.close(p['thread']); api.close(p['process'])
        (root/'ready').write_text('1')
        while True: time.sleep(.01)
    (root/'ready').write_text('1')
    if mode == 'healthy': return
    while True: time.sleep(.01)


def contain(root, mode='healthy', *, budget=.8, cleanup=2., fault=None):
    """TEMPORARY controller; deadline independent of coordinator filesystem IPC."""
    api = API(); job = None; coordinator = None; owned = {}
    status = 'COMPLETE'; cleanup_verified = True; issues = []
    started = time.monotonic(); deadline = started+budget
    max_members = 0; observed_descendants = 0; image_kinds=[]
    try:
        job = api.create_job()
        coordinator = api.spawn(root,'coordinator',mode)
        owned[coordinator['pid']] = coordinator['process']
        if fault == 'assign': api.fault = fault
        api.assign(job, coordinator)
        api.resume(coordinator)
        while True:
            if time.monotonic() >= deadline:
                status = 'DEADLINE'; break
            if mode == 'cancel' and time.monotonic()-started >= .2:
                status = 'CANCELLED'; break
            ids = api.members(job)
            max_members = max(max_members,len(ids))
            for pid in ids:
                if pid not in owned:
                    h = api.open(pid)
                    if not api.member(job,h): raise RuntimeError('MEMBERSHIP_UNKNOWN')
                    owned[pid] = h; observed_descendants += 1
                    image_kinds.append(api.image_kind(h))
            if not ids:
                if not api.wait(coordinator['process'],deadline): raise RuntimeError('EXIT_UNKNOWN')
                if api.exit_code(coordinator['process']) != 0: raise RuntimeError('CHILD_FAILED')
                break
            time.sleep(.005)  # no child IPC read/open/write on the enforcement path
    except Exception as exc:
        status = 'ERROR'; issues.append(type(exc).__name__)
    finally:
        cleanup_started = time.monotonic(); cleanup_deadline = cleanup_started+cleanup
        if fault in ('terminate','query','wait','close'): api.fault = fault
        try:
            if coordinator and not coordinator['assigned']:
                # Sole owned suspended process, never resumed on failed assignment.
                api.checked(api.k.TerminateProcess(coordinator['process'],98))
            if job:
                api.terminate(job)
                while api.members(job):
                    if time.monotonic() >= cleanup_deadline: raise TimeoutError('JOB_NOT_EMPTY')
                    time.sleep(.005)
            for h in owned.values():
                if not api.wait(h,cleanup_deadline): raise TimeoutError('OWNED_EXIT_UNKNOWN')
        except Exception as exc:
            cleanup_verified = False; issues.append(type(exc).__name__)
        # Do not discard exit-observation handles when cleanup is unverified.
        # Preserve them for explicit fixture recovery, never a successful result.
        if cleanup_verified:
            closing = [h for h in api.handles if h != job] + ([job] if job else [])
            for h in closing:
                try: api.close(h)
                except Exception as exc:
                    cleanup_verified = False; issues.append(type(exc).__name__)
        if api.handles or time.monotonic()>cleanup_deadline: cleanup_verified=False
        result = {'status':status,'cleanup_verified':cleanup_verified,'success':status=='COMPLETE' and cleanup_verified and time.monotonic()<=deadline,
                  'issues':issues,'image_kinds':image_kinds,'maximum_members':max_members,'descendants_observed':observed_descendants,
                  'handles_remaining_at_boundary':len(api.handles),'elapsed':time.monotonic()-started,
                  'cleanup_elapsed':time.monotonic()-cleanup_started}
        # Fixture recovery only: never changes the candidate result. Check real
        # job emptiness and every still-retained owned process handle, then close.
        api.fault=None
        rescue_deadline=time.monotonic()+3
        if job and job in api.handles:
            api.checked(api.k.TerminateJobObject(job,99))
            while api.members(job):
                if time.monotonic()>=rescue_deadline: raise RuntimeError('FIXTURE_JOB_LEAK')
                time.sleep(.005)
        for h in owned.values():
            if h in api.handles and not api.wait(h,rescue_deadline): raise RuntimeError('FIXTURE_PROCESS_LEAK')
        for h in list(api.handles): api.close(h)
        result['fixture_handles_remaining']=len(api.handles)
        result['fixture_recovery_verified']=True
        # Optional test metadata ONLY after all worker exits and handle cleanup;
        # never read coordinator IPC on the deadline/cleanup enforcement path.
        roles=[read_small(path) for path in root.glob('role-*.json')]
        result['leaf_roles']=sum(r['role']=='leaf' for r in roles)
        result['roles_in_job']=all(r['pid'] in owned for r in roles)
    return result


def benchmark_block(revision):
    text=(HERE.parent.parent/'docs/ross/NATURAL_READONLY_CHECKPOINT.md').read_text(encoding='utf-8')
    if revision=='v1':
        section=text.split('## 30 October 2026 — Actual Windows containment passed;',1)[1]
    else:
        section=text.split('### Corrected full-path benchmark candidate V2',1)[1]
    block=section.split('```powershell\n',1)[1].split('\n```',1)[0]+'\n'
    if revision=='v1' and hashlib.sha256(block.encode()).hexdigest()!='8226316440f5b1dac0b25b79a3b8b0a8e18a35012c375e4c855335d890089b3d':
        raise AssertionError('Frozen released block changed')
    return block


def native_fixture_run(argv,root,*,budget=30):
    """Bounded outer TEST ownership, not the benchmark's fixed10-member job.

    Host PowerShell + environment-controller launchers can add <=6 members to
    inner capped10. Outer16 is explicit fixture containment, not a benchmark cap
    increase. No network or operational source executed.
    """
    api=API(); job=None; process=None
    end=time.monotonic()+budget
    try:
        job=api.create_job()
        limits=EXTENDED(); limits.BasicLimitInformation.LimitFlags=0x2000|0x8
        limits.BasicLimitInformation.ActiveProcessLimit=16
        api.checked(api.k.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)))
        process=api.spawn_argv(root,argv)
        api.assign(job,process); api.resume(process)
        if not api.wait(process['process'],end): raise AssertionError('Synthetic host exceeded budget')
        return api.exit_code(process['process'])
    finally:
        cleanup_end=time.monotonic()+5
        if process and not process['assigned']: api.checked(api.k.TerminateProcess(process['process'],99))
        if job:
            api.checked(api.k.TerminateJobObject(job,99))
            class OuterMembers(ctypes.Structure):
                _fields_=[('assigned',W.DWORD),('count',W.DWORD),('pids',ctypes.c_size_t*16)]
            while True:
                info=OuterMembers()
                api.checked(api.k.QueryInformationJobObject(job,3,ctypes.byref(info),ctypes.sizeof(info),None))
                if info.count==0: break
                if time.monotonic()>=cleanup_end: raise AssertionError('Synthetic outer job leaked')
                time.sleep(.005)
        if process and not api.wait(process['process'],cleanup_end): raise AssertionError('Synthetic host exit unknown')
        for h in list(api.handles): api.close(h)
        if api.handles: raise AssertionError('Synthetic host handles leaked')


@unittest.skipUnless(os.name=='nt','Actual full Windows PowerShell/benchmark path required')
class FullBenchmarkPath(unittest.TestCase):
    def fixture(self,root):
        repo=root/'source'; repo.mkdir()
        owner=(HERE.parent.parent/'scripts/certification/natural_readonly_operator.py').read_bytes()
        # Checkout CRLF normalization may differ; accepted Git blob uses LF.
        owner=owner.replace(b'\r\n',b'\n')
        self.assertEqual(hashlib.sha1(b'blob '+str(len(owner)).encode()+b'\0'+owner).hexdigest(),'4bec6f8974062cbd68f5c88bbf9baa671a075237')
        path=repo/'scripts/certification'; path.mkdir(parents=True)
        (path/'natural_readonly_operator.py').write_bytes(owner)
        for index in range(2685): (repo/('synthetic-%04d'%index)).write_bytes(b'PRIVATE_CONTENT_CANARY\x00'+str(index).encode())
        git=shutil.which('git')
        self.assertIsNotNone(git)
        for args in (['-c','init.defaultBranch=main','init','-q'],['-c','core.autocrlf=false','add','.'],['-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid','commit','-qm','synthetic']):
            self.assertEqual(native_fixture_run([git,*args],repo),0)
        pin=(repo/'.git/refs/heads/main').read_text().strip()
        obj=zlib.decompress((repo/'.git/objects'/pin[:2]/pin[2:]).read_bytes())
        tree=obj.split(b'\0',1)[1].splitlines()[0].decode().split()[1]
        env=root/'venv'
        self.assertEqual(native_fixture_run([sys.executable,'-I','-S','-B','-m','venv','--without-pip',str(env)],root),0)
        return repo,pin,tree,env/'Scripts/python.exe'

    def run_block(self,root,repo,pin,tree,python,revision,*,workers=None):
        case=root/('case-'+revision+'-'+str(workers)); case.mkdir()
        block=benchmark_block(revision)
        # Test data binding ONLY: same full PowerShell and embedded Python paths,
        # constants/paths rebound to a synthetic2686-file Git fixture, never source.
        substitutions={r'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe':str(python).replace("'","''"),
                       r'C:\tmp\ro-9a2e923d\s':str(repo).replace("'","''"),
                       'a501c88bcc926bef87875f6352f210b19b6e438b':pin,
                       'e66b6daa84f04ec95dce1155fde2a9a4e156cf14':tree}
        scratch_literal=r"Join-Path 'C:\tmp'"
        self.assertEqual(block.count(scratch_literal),1)
        block=block.replace(scratch_literal,"Join-Path '"+str(case).replace("'","''")+"'")
        self.assertNotIn(scratch_literal,block)
        for old,new in substitutions.items():
            self.assertIn(old,block); block=block.replace(old,new)
        if workers is not None:
            self.assertIn('WORKERS=2',block)
            block=block.replace('WORKERS=2','WORKERS='+str(workers))
        script=case/'block.ps1'; script.write_text(block,encoding='utf-8-sig')
        def quote(path): return "'"+str(path).replace("'","''")+"'"
        wrapper=case/'invoke.ps1'
        wrapper.write_text("$ErrorActionPreference='Stop'\ntry { & "+quote(script)+" *> "+quote(case/'console.PRIVATE.log')+"; exit 0 } catch { exit 1 }\n",encoding='utf-8-sig')
        powershell=str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
        code=native_fixture_run([powershell,'-NoProfile','-NonInteractive','-File',str(wrapper)],case,budget=140)
        roots=list(case.glob('manifest-contained-*')); self.assertEqual(len(roots),1)
        output=roots[0]/'manifest-process-shareable.json'
        report=read_small(output)  # <4096 for these aggregate fixtures
        self.assertNotIn('PRIVATE_CONTENT_CANARY',output.read_text())
        self.assertLessEqual(output.stat().st_size,8192)
        self.assertEqual(report['native_member_cap'],10)
        self.assertTrue(report['cleanup_verified'])
        self.assertLessEqual(report['peak_native_members'],10)
        print('FULL_WINDOWS_BENCHMARK',revision,workers,json.dumps(report),flush=True)
        return code,report,roots[0]

    def test_full_powershell_venv_topology_and_reduced_workers(self):
        with tempfile.TemporaryDirectory(prefix='full-manifest-path-') as text:
            root=Path(text); repo,pin,tree,python=self.fixture(root)
            old_code,old,_=self.run_block(root,repo,pin,tree,python,'v1')
            diagnosed_code,diagnosed,_=self.run_block(root,repo,pin,tree,python,'v2',workers=4)
            good_code,good,private=self.run_block(root,repo,pin,tree,python,'v2')
            # Collect all bounded diagnostics before assertions; an early fixture
            # prerequisite error is NOT a reproduction of cap exhaustion.
            self.assertNotEqual(old_code,0); self.assertEqual(old['status'],'FAIL')
            self.assertNotEqual(diagnosed_code,0); self.assertEqual(diagnosed['status'],'FAIL')
            self.assertTrue(diagnosed['failure_evidence_available'])
            self.assertGreaterEqual(diagnosed['failure_stage'],40,'Synthetic prerequisite failed before worker topology')
            self.assertEqual(old['peak_native_members'],10)
            self.assertEqual(good_code,0); self.assertEqual(good['status'],'COMPLETE')
            self.assertEqual(good['logical_workers_configured'],2)
            self.assertEqual(good['workers'],2); self.assertLessEqual(good['peak_pending'],2)
            manifest=json.loads((private/'manifest.COMPLETE.PRIVATE.json').read_text())
            owner=(repo/'scripts/certification/natural_readonly_operator.py').read_text()
            node=next(n for n in ast.parse(owner).body if isinstance(n,ast.FunctionDef) and n.name=='digest')
            namespace={'hashlib':hashlib}
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-digest>','exec'),namespace)
            expected={p.relative_to(repo).as_posix():namespace['digest'](p) for p in sorted(repo.rglob('*')) if p.is_file() and '.git' not in p.relative_to(repo).parts}
            self.assertEqual(manifest,expected)
            self.assertEqual(list(manifest),sorted(expected))
            self.assertEqual(len(manifest),2686)
            print('FULL_WINDOWS_EQUIVALENCE 2686 fresh synthetic hashes identical',flush=True)


@unittest.skipUnless(os.name == 'nt', 'Actual Windows APIs required; Linux is not validation')
class WindowsContainment(unittest.TestCase):
    def test_complete_and_deadline_cases(self):
        with tempfile.TemporaryDirectory(prefix='manifest-containment-') as text:
            base=Path(text)
            for mode in ('healthy','stall','startup','ipc','descendants','partial','breakaway','cancel'):
                with self.subTest(mode=mode):
                    root=base/mode; root.mkdir()
                    r=contain(root,mode,budget=2. if mode=='healthy' else 1.)
                    print('WINDOWS_CONTAINMENT',mode,json.dumps(r),flush=True)
                    self.assertTrue(r['cleanup_verified']); self.assertEqual(r['fixture_handles_remaining'],0)
                    if mode=='healthy': self.assertTrue(r['success'])
                    else: self.assertEqual(r['status'],'CANCELLED' if mode=='cancel' else 'DEADLINE'); self.assertFalse(r['success'])
                    if mode=='descendants': self.assertGreaterEqual(r['maximum_members'],3); self.assertLessEqual(r['maximum_members'],MAX_MEMBERS); self.assertEqual(r['leaf_roles'],2); self.assertTrue(r['roles_in_job'])
                    if mode=='partial': self.assertGreaterEqual(r['maximum_members'],2); self.assertLessEqual(r['maximum_members'],MAX_MEMBERS); self.assertEqual(r['leaf_roles'],1); self.assertTrue(r['roles_in_job'])
                    if mode=='breakaway': self.assertTrue((root/'breakaway-denied').exists())

    def test_failure_paths_never_publish_success(self):
        with tempfile.TemporaryDirectory(prefix='manifest-containment-') as text:
            for fault in ('assign','terminate','query','wait','close'):
                with self.subTest(fault=fault):
                    root=Path(text)/fault; root.mkdir()
                    r=contain(root,'stall',budget=.5,fault=fault)
                    print('WINDOWS_FAULT',fault,json.dumps(r),flush=True)
                    self.assertFalse(r['success']); self.assertEqual(r['fixture_handles_remaining'],0)
                    if fault=='assign':
                        self.assertEqual(r['status'],'ERROR'); self.assertTrue(r['cleanup_verified'])
                        self.assertFalse((root/'ready').exists(),'Assignment failure resumed suspended child')
                    else: self.assertFalse(r['cleanup_verified'])

    def test_controller_exit_kills_job_and_not_unrelated_process(self):
        api=API(); processes=[]; held=[]
        with tempfile.TemporaryDirectory(prefix='manifest-containment-') as text:
            root=Path(text)
            try:
                unrelated=api.spawn(root,'leaf','unrelated',suspended=False); processes.append(unrelated)
                controller=api.spawn(root,'exit-controller','exit',suspended=False); processes.append(controller)
                end=time.monotonic()+15
                while not (root/'controller-ready').exists() and time.monotonic()<end: time.sleep(.01)
                proof=read_small(root/'controller-ready')
                self.assertGreaterEqual(len(proof),3); self.assertLessEqual(len(proof),MAX_MEMBERS)
                for row in proof:
                    h=api.open(row['pid']); held.append(h)
                    self.assertEqual(api.token(h),row['creation'])
                (root/'exit-controller').write_text('1')
                end=time.monotonic()+3  # ONE shared deadline for controller+descendants
                self.assertTrue(api.wait(controller['process'],end))
                for h in held: self.assertTrue(api.wait(h,end))
                self.assertFalse(api.wait(unrelated['process'],time.monotonic()+.03))
                print('WINDOWS_KILL_ON_CLOSE',len(proof),'members_exited unrelated_alive',flush=True)
            finally:
                for p in processes:
                    if not api.wait(p['process'],time.monotonic()): api.checked(api.k.TerminateProcess(p['process'],99))
                    self.assertTrue(api.wait(p['process'],time.monotonic()+3))
                for h in list(api.handles): api.close(h)
                self.assertFalse(api.handles)

    def test_exit_controller_assignment_failure_retires_unassigned_child(self):
        api=API(); controller=None; held=None
        with tempfile.TemporaryDirectory(prefix='manifest-containment-') as text:
            root=Path(text)
            try:
                controller=api.spawn(root,'exit-controller','assign-fail',suspended=False)
                end=time.monotonic()+10
                while not (root/'unassigned').exists() and time.monotonic()<end: time.sleep(.005)
                proof=read_small(root/'unassigned')
                held=api.open(proof['pid'])
                self.assertEqual(api.token(held),proof['creation'])
                (root/'continue-assignment').write_text('1')
                end=time.monotonic()+3
                self.assertTrue(api.wait(controller['process'],end))
                self.assertNotEqual(api.exit_code(controller['process']),0)
                self.assertTrue(api.wait(held,end))
                self.assertFalse((root/'ready').exists())
                print('WINDOWS_ASSIGN_FAILURE unassigned_suspended_child_retired',flush=True)
            finally:
                if held and not api.wait(held,time.monotonic()):
                    api.checked(api.k.TerminateProcess(held,99))
                    self.assertTrue(api.wait(held,time.monotonic()+3))
                if controller and not api.wait(controller['process'],time.monotonic()):
                    api.checked(api.k.TerminateProcess(controller['process'],99))
                    self.assertTrue(api.wait(controller['process'],time.monotonic()+3))
                for h in list(api.handles): api.close(h)
                self.assertFalse(api.handles)

    def test_second_native_start_failure_does_not_leak_first_leaf(self):
        api=API(); first=None
        with tempfile.TemporaryDirectory(prefix='manifest-containment-') as text:
            root=Path(text)
            try:
                first=api.spawn(root,'leaf','unrelated',suspended=False)
                with self.assertRaises(OSError):
                    api.spawn(root/'nonexistent-current-directory','exit-controller','exit',suspended=False)
            finally:
                if first:
                    api.checked(api.k.TerminateProcess(first['process'],99))
                    self.assertTrue(api.wait(first['process'],time.monotonic()+3))
                for h in list(api.handles): api.close(h)
                self.assertFalse(api.handles)
            print('WINDOWS_PARTIAL_START first_leaf_retired_after_second_create_failure',flush=True)

    def test_native_invalid_handle_errors_are_not_success(self):
        api=API()
        for operation in (lambda:api.k.AssignProcessToJobObject(None,None),
                          lambda:api.k.TerminateJobObject(None,1),
                          lambda:api.k.QueryInformationJobObject(None,3,None,0,None),
                          lambda:api.k.CloseHandle(None)):
            self.assertFalse(operation())
            self.assertNotEqual(ctypes.get_last_error(),0)
        self.assertEqual(api.k.WaitForSingleObject(None,0),0xFFFFFFFF)
        print('WINDOWS_NATIVE invalid_terminate_query_wait_close_failed',flush=True)


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child':
        child(Path(sys.argv[2]),sys.argv[3],sys.argv[4])
    else:
        unittest.main(verbosity=2)
