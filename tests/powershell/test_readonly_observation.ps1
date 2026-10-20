# Actual Windows PowerShell, controlled children only. No natural runtime/acquisition.
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSEdition -ne 'Desktop') { throw 'Requires actual Windows PowerShell.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'scripts\certification\Invoke-ReadonlyObservation.ps1')
$tempRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$scratch = Join-Path $tempRoot ('ps-observation-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $scratch | Out-Null
$passed = 0
function Check($ok, $text) { if (!$ok) { throw $text } }
$stub = Join-Path $scratch "stub 'quoted'.py"
@'
import json, os, pathlib, sys, time, zipfile
phase, root, head = sys.argv[1:]
p = pathlib.Path(root); e=p/'e'; e.mkdir(exist_ok=True)
with (e/'phases').open('a') as out: out.write(phase+'\n')
case=os.environ.get('OBS_TEST_CASE','success')
print('STDOUT '+phase, flush=True); print('STDERR '+phase, file=sys.stderr, flush=True)
if phase == 'preflight':
    if case in ('preflight','preflight-package-failure'):
        (e/'preflight-result.json').write_text(json.dumps(dict(status='FAIL',stage='initial_runtime_inventory',reason='controlled timeout',exit_code=2)))
    if case=='preflight-stuck':
        (e/'pid').write_text(str(os.getpid())); time.sleep(15)
    sys.exit(2 if case in ('preflight','preflight-package-failure') else 0)
if phase == 'observe':
    if case in ('stop', 'stuck'):
        (e/'pid').write_text(str(os.getpid()))
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if case=='stop' and (e/'terminal'/'STOP_REQUESTED').exists(): break
            time.sleep(.02)
        print('STOPPED', flush=True)
    if case=='pipes':
        print('o'*200000); print('e'*200000, file=sys.stderr)
    sys.exit({'failure':1,'collection':2,'native7':7}.get(case,0))
if phase == 'seal':
    if case=='seal-failure': sys.exit(9)
    with zipfile.ZipFile(p/'ross-natural-readonly-upload.zip','a') as z: z.write(e/'phase-status.json','phase-status.json')
    sys.exit(0)
if phase == 'package':
    if case in ('package','preflight-package-failure'): sys.exit(9)
    with zipfile.ZipFile(p/'stub.zip','w') as z: z.write(e/'phases','phases')
    (p/'ross-natural-readonly-upload.zip').write_bytes((p/'stub.zip').read_bytes())
    sys.exit(0)
'@ | Set-Content -Encoding utf8 $stub
try {
    foreach ($script in @('scripts\certification\Invoke-ReadonlyObservation.ps1','scripts\certification\run_natural_readonly_observation.ps1','docs\ross\PR1108_NATURAL_READONLY_ACCEPTANCE.ps1')) {
        $errors=$null; $tokens=$null
        $null=[Management.Automation.Language.Parser]::ParseFile((Join-Path $repo $script),[ref]$tokens,[ref]$errors)
        Check ($errors.Count -eq 0) "Parse failure $script"
    }
    $passed++
    foreach ($case in @('success','preflight','preflight-package-failure','failure','collection','native7','pipes','package','seal-failure','stop')) {
        $env:OBS_TEST_CASE=$case
        $root=Join-Path $scratch $case; New-Item -ItemType Directory $root | Out-Null
        $budget=if ($case -eq 'stop') { .3 } else { 10 }
        $result=Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -ObservationSeconds $budget -StopSeconds 2
        $expected=@{success=0;preflight=2;'preflight-package-failure'=2;failure=1;collection=2;native7=7;pipes=0;package=9;'seal-failure'=1;stop=124}[$case]
        Check ($result -eq $expected) "$case exit $result != $expected"
        $phases=Get-Content (Join-Path $root 'e\phases')
        Check ($phases[-1] -eq $(if ($case -in @('package','preflight-package-failure')) {'package'} else {'seal'})) "$case did not package"
        if ($case -in @('preflight','preflight-package-failure')) { Check (!($phases -contains 'observe')) 'Preflight failure launched observation.' }
        if ($case -notin @('package','preflight-package-failure')) { Check (Test-Path (Join-Path $root 'stub.zip')) 'Missing ZIP.' }
        if ($case -notin @('preflight','preflight-package-failure')) {
            Check ((Get-Content -Raw (Join-Path $root 'e\supervisor.stdout.log')) -match 'STDOUT observe') 'stdout lost'
            Check ((Get-Content -Raw (Join-Path $root 'e\supervisor.stderr.log')) -match 'STDERR observe') 'stderr lost'
        }
        if ($case -eq 'stop') { Check (Test-Path (Join-Path $root 'e\terminal\STOP_REQUESTED')) 'No bounded cooperative stop.' }
        $status=Get-Content -Raw (Join-Path $root 'e\phase-status.json') | ConvertFrom-Json
        Check ($status.final_exit -eq $expected) 'Final phase receipt disagrees.'
        if ($case -eq 'preflight-package-failure') {
            Check ($status.preflight_exit -eq 2 -and $status.package_exit -eq 9) 'Packaging masked preflight failure.'
        }
        $passed++
    }
    $preserved=Join-Path $scratch 'existing-root'; New-Item -ItemType Directory (Join-Path $preserved 'e') | Out-Null
    'KEEP' | Set-Content (Join-Path $preserved 'e\receipt.txt')
    $failed=$false
    try { Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $preserved -ExpectedCommit ('a'*40) | Out-Null } catch { $failed=$true }
    Check ($failed -and (Get-Content -Raw (Join-Path $preserved 'e\receipt.txt')) -match 'KEEP') 'Existing evidence was overwritten.'
    $passed++
    # Launch and log-open failures must not start the child.
    foreach ($case in @('launch','log-open')) {
        $root=Join-Path $scratch $case; New-Item -ItemType Directory $root | Out-Null
        $prefix=Join-Path $root 'child'
        if ($case -eq 'log-open') { New-Item -ItemType Directory ($prefix+'.stdout.log') | Out-Null }
        $failed=$false
        try {
            $exe=if ($case -eq 'launch') { Join-Path $root 'missing.exe' } else { $Python }
            Invoke-ObservationChild -Python $exe -ChildArguments @('-E',$stub,'observe',$root,('a'*40)) -LogPrefix $prefix -BudgetSeconds 1 | Out-Null
        } catch { $failed=$true }
        Check $failed "$case falsely passed"
        Check (!(Test-Path (Join-Path $root 'e\phases'))) "$case launched child"
        $passed++
    }
    # Uncooperative controlled child: bounded return, no packaging while alive.
    $env:OBS_TEST_CASE='stuck'; $root=Join-Path $scratch 'stuck'; New-Item -ItemType Directory $root | Out-Null
    $clock=[Diagnostics.Stopwatch]::StartNew(); $failed=$false
    try { Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -ObservationSeconds .3 -StopSeconds 1 | Out-Null } catch { $failed=$true }
    Check ($failed -and $clock.Elapsed.TotalSeconds -lt 2.1) 'Uncooperative stop was not bounded.'
    Check (!(Test-Path (Join-Path $root 'stub.zip'))) 'Packaged while child alive.'
    $stubPid=[int](Get-Content (Join-Path $root 'e\pid'))
    Stop-Process -Id $stubPid -ErrorAction SilentlyContinue # Owned synthetic child only.
    $passed++
    $env:OBS_TEST_CASE='preflight-stuck'; $root=Join-Path $scratch 'preflight-stuck'
    New-Item -ItemType Directory $root | Out-Null
    $failed=$false; $clock=[Diagnostics.Stopwatch]::StartNew()
    try { Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -PreflightSeconds .3 -StopSeconds .3 | Out-Null } catch { $failed=$true }
    Check ($failed -and $clock.Elapsed.TotalSeconds -lt 5) 'Stuck preflight was not bounded.'
    Check (!(Test-Path (Join-Path $root 'stub.zip'))) 'Packaged while preflight alive.'
    $stubPid=[int](Get-Content (Join-Path $root 'e\pid'))
    Stop-Process -Id $stubPid -ErrorAction SilentlyContinue
    $passed++
    # A controlled faulting stream exercises the same async log-copy boundary.
    Add-Type @'
using System;
using System.IO;
public class ObservationFaultStream : Stream {
 public override bool CanRead { get { return false; } }
 public override bool CanSeek { get { return false; } }
 public override bool CanWrite { get { return true; } }
 public override long Length { get { return 0; } }
 public override long Position { get { return 0; } set { throw new NotSupportedException(); } }
 public override void Flush() { }
 public override int Read(byte[] b,int o,int c) { throw new NotSupportedException(); }
 public override long Seek(long o,SeekOrigin s) { throw new NotSupportedException(); }
 public override void SetLength(long v) { throw new NotSupportedException(); }
 public override void Write(byte[] b,int o,int c) { throw new IOException("controlled log write failure"); }
}
'@
    $env:OBS_TEST_CASE='stop'; $root=Join-Path $scratch 'log-write'; New-Item -ItemType Directory $root | Out-Null
    $stop=Join-Path $root 'e\terminal\STOP_REQUESTED'; $failed=$false; $exited=$false
    try {
        Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$stub,'observe',$root,('a'*40)) -LogPrefix (Join-Path $root 'log') -StopPath $stop -BudgetSeconds 4 -StopSeconds 2 -LogStreamFactory { param($path) New-Object ObservationFaultStream } | Out-Null
    } catch { $failed=$true; $exited=[bool]$_.Exception.Data['ChildExited'] }
    Check ($failed -and $exited -and (Test-Path $stop)) 'Log-write failure did not stop child/fail closed.'
    $passed++
    # Execute the released PowerShell entrypoint in its own real powershell.exe,
    # replacing only its fixed Python child with a synthetic fixture copy.
    $entry=Join-Path $scratch 'entry'; New-Item -ItemType Directory $entry | Out-Null
    Copy-Item (Join-Path $repo 'scripts\certification\run_natural_readonly_observation.ps1') $entry
    Copy-Item (Join-Path $repo 'scripts\certification\Invoke-ReadonlyObservation.ps1') $entry
    Copy-Item $stub (Join-Path $entry 'natural_readonly_operator.py')
    foreach ($case in @('success','collection','failure','preflight','seal-failure')) {
        $env:OBS_TEST_CASE=$case; $root=Join-Path $scratch ('entry-'+$case); New-Item -ItemType Directory $root | Out-Null
        $child=Invoke-ObservationChild -Python (Get-Command powershell.exe).Source -ChildArguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $entry 'run_natural_readonly_observation.ps1'),'-Python',$Python,'-Root',$root,'-ExpectedCommit',('a'*40)) -LogPrefix (Join-Path $scratch ('entry-'+$case)) -BudgetSeconds 20
        $expected=@{success=0;collection=2;failure=1;preflight=2;'seal-failure'=1}[$case]
        Check ($child.ExitCode -eq $expected) "Released entrypoint did not preserve $case OS status."
        if ($case -eq 'seal-failure') {
            $report=Get-Content -Raw (Join-Path $scratch ('entry-'+$case+'.stdout.log'))
            Check ($report -notmatch 'DIAGNOSTIC ZIP:' -and $report -match 'Archive sealing failed') 'Unsealed archive was announced.'
        }
        if ($case -eq 'preflight') {
            $report=Get-Content -Raw (Join-Path $scratch ('entry-'+$case+'.stdout.log'))
            Check ($report -match 'Preflight failed at initial_runtime_inventory: controlled timeout') 'Actual preflight reason lost.'
            Check ($report -match 'Package exit: 0' -and $report -match 'DIAGNOSTIC ZIP:' -and $report -match 'Final exit: 2') 'Diagnostic path/status not surfaced.'
        }
        $passed++
    }
    # Real local Git worktree preparation, including dirty source and old evidence.
    # No network fetch/clone, no operator child is invoked.
    $source=Join-Path $scratch 'local-source'; New-Item -ItemType Directory $source | Out-Null
    & git -C $source init -q
    'original' | Set-Content (Join-Path $source 'sentinel.txt')
    & git -C $source add .
    & git -C $source -c user.name=Harness -c user.email=harness@example.invalid commit -qm fixture
    Check ($global:LASTEXITCODE -eq 0) 'Fixture commit failed.'
    $localHead=(& git -C $source rev-parse HEAD | Out-String).Trim()
    'dirty source retained' | Set-Content (Join-Path $source 'sentinel.txt')
    $prepBase=Join-Path $scratch 'prepared'; New-Item -ItemType Directory $prepBase | Out-Null
    $old=Join-Path $prepBase 'old-evidence'; New-Item -ItemType Directory $old | Out-Null
    'KEEP' | Set-Content (Join-Path $old 'receipt.txt')
    $LASTEXITCODE=361
    $prepared=& (Join-Path $repo 'docs\ross\PR1108_NATURAL_READONLY_ACCEPTANCE.ps1') -ExpectedCommit $localHead -Python $Python -SourceCheckout $source -BaseDirectory $prepBase 6>&1
    Check ($LASTEXITCODE -eq 361) 'Caller-local status was unexpectedly changed.'
    $preparedRoot=Get-ChildItem -Directory $prepBase | Where-Object { $_.Name -like 'ro-*' } | Select-Object -First 1
    Check ($null -ne $preparedRoot) 'Preparation did not create worktree.'
    $checkout=Join-Path $preparedRoot.FullName 's'
    Check (Test-Path -LiteralPath (Join-Path $checkout '.git') -PathType Leaf) 'Expected shared Git worktree, not full clone.'
    Check (!(Test-Path (Join-Path $preparedRoot.FullName 'e'))) 'Preparation launched preflight/runtime.'
    Check ((Get-Content -Raw (Join-Path $source 'sentinel.txt')) -match 'dirty source retained') 'Source changed.'
    Check ((Get-Content -Raw (Join-Path $old 'receipt.txt')) -match 'KEEP') 'Existing evidence changed.'
    Check (($prepared | Out-String) -match 'run_natural_readonly_observation.ps1') 'No separate execution command printed.'
    & git -C $source worktree remove --force $checkout
    Check ($global:LASTEXITCODE -eq 0) 'Synthetic worktree cleanup failed.'
    $passed++
    # Actual startup semantics: -E parent ignores PYTHONPATH; its ordinary child
    # loads the copied hook and configures only a private fake-provider cache.
    $startup=Join-Path $scratch 'startup'; $fake=Join-Path $scratch 'fake'
    New-Item -ItemType Directory $startup,(Join-Path $fake 'yfinance') | Out-Null
    Copy-Item (Join-Path $repo 'scripts\certification\readonly_cache_sitecustomize.py') (Join-Path $startup 'sitecustomize.py')
    '' | Set-Content (Join-Path $fake 'yfinance\__init__.py')
    @'
import os, pathlib
class _Manager:
    location = None
    @classmethod
    def get_location(cls): return cls.location
class _TzDBManager(_Manager): pass
class _CookieDBManager(_Manager): pass
class _ISINDBManager(_Manager): pass
def set_cache_location(path):
    if os.environ.get('CACHE_FAIL'): raise RuntimeError('controlled configuration failure')
    for manager in (_TzDBManager,_CookieDBManager,_ISINDBManager): manager.location=path
    pathlib.Path(path).mkdir(exist_ok=True)
    (pathlib.Path(path)/'configured').write_text('private')
'@ | Set-Content (Join-Path $fake 'yfinance\cache.py')
    $probe=Join-Path $scratch 'probe.py'
    @'
import os, pathlib, subprocess, sys
assert sys.flags.ignore_environment
assert 'sitecustomize' not in sys.modules
startup,fake,private=sys.argv[1:]
env=dict(os.environ, PYTHONPATH=os.pathsep.join((startup,fake)),PR1108_YFINANCE_CACHE=private)
code="import yfinance.cache as c; assert c._readonly_cache_isolated; print('ISOLATED')"
r=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True)
assert r.returncode==0 and 'ISOLATED' in r.stdout,(r.returncode,r.stdout,r.stderr)
assert (pathlib.Path(private)/'configured').is_file()
r=subprocess.run([sys.executable,'-E','-c',"import sys; assert 'sitecustomize' not in sys.modules"],env=env)
assert r.returncode==0
broken=pathlib.Path(fake).parent/'broken'
(broken/'yfinance').mkdir(parents=True)
(broken/'yfinance'/'__init__.py').write_text('raise ImportError("controlled missing provider")')
for change in ({'CACHE_FAIL':'1'},{'PR1108_YFINANCE_CACHE':'relative'},
               {'PYTHONPATH':os.pathsep.join((startup,str(broken)))}):
    r=subprocess.run([sys.executable,'-c','raise SystemExit(0)'],env=dict(env,**change))
    assert r.returncode==78,r.returncode
# Installed real yfinance: inspect cache-manager paths only; never fetch.
r=subprocess.run([sys.executable,'-c',code+'; print(c._readonly_cache_locations)'],
                 env=dict(env,PYTHONPATH=startup),capture_output=True,text=True)
assert r.returncode==0 and 'ISOLATED' in r.stdout,(r.returncode,r.stdout,r.stderr)
print('REAL_PROVIDER_CACHE_LOCATIONS',r.stdout)
print('CACHE_STARTUP_CHECKS_PASS')
'@ | Set-Content $probe
    $result=Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$probe,$startup,$fake,(Join-Path $scratch 'private-cache')) -LogPrefix (Join-Path $scratch 'startup-probe') -BudgetSeconds 15
    Check ($result.ExitCode -eq 0) 'Cache startup semantics failed.'
    Get-Content ($scratch+'\startup-probe.stdout.log') | Where-Object { $_ -match 'CACHE_STARTUP_CHECKS_PASS|REAL_PROVIDER_CACHE_LOCATIONS' } | ForEach-Object { Write-Host $_ }
    $passed++
    $inventory=Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',(Join-Path $repo 'tests\powershell\verify_windows_inventory.py')) -LogPrefix (Join-Path $scratch 'inventory') -BudgetSeconds 60
    Check ($inventory.ExitCode -eq 0) 'Windows inventory checks failed.'
    Get-Content ($scratch+'\inventory.stdout.log') | ForEach-Object { Write-Host $_ }
    $passed++
    # Real packaging implementation with synthetic terminal/inventory; no supervisor.main.
    $result=Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',(Join-Path $repo 'tests\powershell\verify_observation_package.py'),$repo,$scratch) -LogPrefix (Join-Path $scratch 'real-package') -BudgetSeconds 45
    Check ($result.ExitCode -eq 0) 'Real package regression failed.'
    Get-Content ($scratch+'\real-package.stdout.log') | Where-Object { $_ -match 'REAL_(PACKAGE|PREFLIGHT)_CHECKS_PASS' } | ForEach-Object { Write-Host $_ }
    $passed++
    @{passed=$passed; powershell=$PSVersionTable.PSVersion.ToString(); platform=$env:OS; scope='controlled stub children only; no providers/broker/runtime'} | ConvertTo-Json | Set-Content (Join-Path $scratch 'receipt.json')
    Write-Host "OBSERVATION_HARNESS_PASS: $passed checks; $scratch"
    exit 0
} finally { Remove-Item Env:OBS_TEST_CASE -ErrorAction SilentlyContinue }
