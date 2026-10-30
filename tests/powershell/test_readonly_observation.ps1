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
import ast, json, os, pathlib, sys, time, zipfile
def no_network(event,args):
    if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('Network forbidden')
sys.addaudithook(no_network)
phase, root, head, *duration_args = sys.argv[1:]
p = pathlib.Path(root); e=p/'e'; e.mkdir(exist_ok=True)
with (e/'durations').open('a') as durations: durations.write(phase+':'+(duration_args[0] if duration_args else '180')+'\n')
with (e/'phases').open('a') as out: out.write(phase+'\n')
case=os.environ.get('OBS_TEST_CASE','success')
print('STDOUT '+phase, flush=True); print('STDERR '+phase, file=sys.stderr, flush=True)
if phase == 'prepare':
    if case=='prepare-failure':sys.exit(3)
    if case=='prepare-late':time.sleep(1)
    if case=='prepare-stuck':
        (e/'pid').write_text(str(os.getpid()));time.sleep(15)
if case=='venv-handoff' and phase in ('prepare','preflight','observe'):
    source=pathlib.Path(os.environ['OBS_TEST_REPO'])/'scripts/certification/natural_readonly_operator.py'
    sys.path.insert(0,os.environ['OBS_TEST_REPO'])
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='require_controller')
    ns=dict(root=p,os=os,json=json,time=time)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
    ns['require_controller']()
if phase == 'preflight':
    if case=='cache-unowned':
        (e/'child-cache-probe.json').write_text(json.dumps(dict(child_exited=False)));sys.exit(1)
    if case=='preflight-late-pass':
        time.sleep(1); (e/'preflight-result.json').write_text(json.dumps(dict(status='PASS',stage='complete',exit_code=0)))
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
    if case=='package-late':time.sleep(1)
    with zipfile.ZipFile(p/'stub.zip','w') as z: z.write(e/'phases','phases')
    (p/'ross-natural-readonly-upload.zip').write_bytes((p/'stub.zip').read_bytes())
    sys.exit(0)
'@ | Set-Content -Encoding utf8 $stub
try {
    # Deterministic near-boundary proof. Observation time is not OS exit time.
    $deadline = [datetime]::UtcNow
    Check (Test-ObservationExitDeadline $deadline ($deadline.AddMilliseconds(-1))) 'Timely near-deadline exit rejected'
    Check (Test-ObservationExitDeadline $deadline $deadline) 'Exact boundary exit rejected'
    Check (!(Test-ObservationExitDeadline $deadline ($deadline.AddMilliseconds(1)))) 'Late completion accepted'
    Check (!(Test-ObservationExitDeadline $deadline $null)) 'Unknown exit time accepted'
    $passed++
    # Real Windows Python children, no repository imports or acquisition. Include
    # cold interpreter startup in the budget, and retain an inner PASS on late exit.
    foreach ($case in @('timely','timely-near','late-pass','expired')) {
        $prefix = Join-Path $scratch $case
        $receipt = $prefix + '.inner.json'
        $delay = if ($case -eq 'timely') { .05 } elseif ($case -eq 'late-pass') { 4.05 } else { 1.0 }
        $budget = if ($case -eq 'expired') { .2 } elseif ($case -in @('timely','timely-near')) { 5.0 } else { 4.0 }
        $mode = 'relative'
        if ($case -eq 'timely-near') {
            # Fixed wall-clock target absorbs variable interpreter startup; OS
            # exit must still prove it actually completed near, and before,5s.
            $delay = ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0) + 4.5
            $mode = 'absolute'
        }
        $delayText = $delay.ToString([Globalization.CultureInfo]::InvariantCulture)
        $code = 'import pathlib,sys,time; delay=float(sys.argv[2]); delay=max(0,delay-time.time()) if sys.argv[3]=="absolute" else delay; time.sleep(delay); pathlib.Path(sys.argv[1]).write_text("PASS"); print("completed",flush=True)'
        $result = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u','-c',$code,$receipt,$delayText,$mode) -LogPrefix $prefix -BudgetSeconds $budget -StopSeconds 5
        $processReceipt = Get-Content -Raw ($prefix+'.process.json') | ConvertFrom-Json
        Check ($result.ExitCode -eq 0 -and $result.Exited) "$case child exit lost"
        Check ((Get-Content -Raw $receipt) -eq 'PASS') "$case inner completion missing"
        if ($case -in @('timely','timely-near')) {
            Check (!$result.TimedOut -and $processReceipt.timely_exit_verified) 'Timely completion mislabeled timeout'
            Check ([datetime]$processReceipt.os_exit_utc -le [datetime]$processReceipt.deadline_utc) 'No timely OS exit proof'
            if ($case -eq 'timely-near') {
                $margin = ([datetime]$processReceipt.deadline_utc - [datetime]$processReceipt.os_exit_utc).TotalSeconds
                Check ($margin -ge 0 -and $margin -le 1) 'Fixture did not actually finish near deadline'
            }
        } else {
            Check ($result.TimedOut -and !$processReceipt.timely_exit_verified) 'Late PASS bypassed deadline'
            Check ([datetime]$processReceipt.os_exit_utc -gt [datetime]$processReceipt.deadline_utc) 'Late OS completion not retained'
        }
        Check ((Get-Content -Raw ($prefix+'.stdout.log')) -match 'completed') "$case output lost"
        $passed++
    }
    foreach ($script in @('scripts\certification\Invoke-ReadonlyObservation.ps1','scripts\certification\run_natural_readonly_observation.ps1','docs\ross\PR1108_NATURAL_READONLY_ACCEPTANCE.ps1')) {
        $errors=$null; $tokens=$null
        $null=[Management.Automation.Language.Parser]::ParseFile((Join-Path $repo $script),[ref]$tokens,[ref]$errors)
        Check ($errors.Count -eq 0) "Parse failure $script"
    }
    $passed++
    $release = Get-Content -Raw (Join-Path $repo 'docs\ross\PR1119_INTEGRATION_RELEASE.md')
    $block = [regex]::Match($release, '(?s)```powershell\r?\n(.*?)\r?\n```').Groups[1].Value
    $parseErrors=$null; $parseTokens=$null
    $null=[Management.Automation.Language.Parser]::ParseInput($block,[ref]$parseTokens,[ref]$parseErrors)
    Check ($block.Length -gt 0 -and $parseErrors.Count -eq 0) 'Release preparation block parse failure'
    Check ($block -notmatch '\$LASTEXITCODE\b') 'Release block uses shadowable native exit status'
    Check ($block -match '-RuntimeSeconds 900') 'Release block does not print a900s observation'
    Check ($block -notmatch 'New-Item[^\r\n]*-Path\s+\$e(?:\s|$)') 'Release block precreates forbidden evidence directory'
    $passed++
    foreach ($case in @('success','preflight','preflight-package-failure','failure','collection','native7','pipes','package','seal-failure','stop')) {
        $env:OBS_TEST_CASE=$case
        $root=Join-Path $scratch $case; New-Item -ItemType Directory $root | Out-Null
        $budget=if ($case -eq 'stop') { .3 } else { 10 }
        $result=Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -ObservationSeconds $budget -StopSeconds 2
        $expected=@{success=0;preflight=2;'preflight-package-failure'=2;failure=1;collection=2;native7=7;pipes=0;package=9;'seal-failure'=1;stop=124}[$case]
        Check ($result -eq $expected) "$case exit $result != $expected"
        $durations=@(Get-Content (Join-Path $root 'e\durations'))
        foreach ($line in $durations) { Check ($line.EndsWith(':180')) 'Default duration changed across child boundary' }
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
    $env:OBS_TEST_CASE='preflight-late-pass'
    $root=Join-Path $scratch 'preflight-late-pass'; New-Item -ItemType Directory $root | Out-Null
    $failed=$false
    try { Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -PreflightSeconds .2 -StopSeconds 3 | Out-Null }
    catch { $failed=$_.Exception.Message -match 'Preflight timed out' }
    Check $failed 'Late inner PASS launched observation'
    $phases=Get-Content (Join-Path $root 'e/phases')
    Check (!($phases -contains 'observe') -and ($phases -contains 'seal')) 'Late PASS launched runtime or lost package'
    $status=Get-Content -Raw (Join-Path $root 'e/phase-status.json') | ConvertFrom-Json
    Check ($status.preflight_exit -eq 0 -and $status.preflight_timed_out -and $status.final_exit -ne 0) 'Contradictory child/outer outcomes not separated'
    Check ($status.outer_reason -match 'deadline failure') 'Actual deadline reason missing'
    $passed++
    foreach ($seconds in @(900,1800)) {
        $env:OBS_TEST_CASE='success'
        $root=Join-Path $scratch ('duration-'+$seconds); New-Item -ItemType Directory $root | Out-Null
        $result=Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -RuntimeSeconds $seconds
        Check ($result -eq 0) "Duration $seconds failed"
        $durations=@(Get-Content (Join-Path $root 'e\durations'))
        Check ($durations.Count -eq 5) 'Duration phases missing'
        foreach ($line in $durations) { Check ($line.EndsWith(':'+[string]$seconds)) 'Duration lost across child boundary' }
        $passed++
    }
    foreach ($seconds in @(179,1801)) {
        $root=Join-Path $scratch ('invalid-duration-'+$seconds); New-Item -ItemType Directory $root | Out-Null
        $failed=$false
        try { Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -RuntimeSeconds $seconds | Out-Null } catch { $failed=$true }
        Check ($failed -and !(Test-Path (Join-Path $root 'e'))) 'Invalid duration started a phase'
        $passed++
    }
    $preserved=Join-Path $scratch 'existing-root'; New-Item -ItemType Directory (Join-Path $preserved 'e') | Out-Null
    'KEEP' | Set-Content (Join-Path $preserved 'e\receipt.txt')
    $failed=$false
    try { Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $preserved -ExpectedCommit ('a'*40) | Out-Null } catch { $failed=$true }
    Check ($failed -and (Get-Content -Raw (Join-Path $preserved 'e\receipt.txt')) -match 'KEEP') 'Existing evidence was overwritten.'
    $passed++

    # Full orchestration through actual Windows venv redirectors, using the
    # released controller-binding function in each child. No runtime/broker.
    $venv = Join-Path $scratch 'handoff-venv'
    & $Python -m venv --without-pip $venv
    Check ($LASTEXITCODE -eq 0) 'Synthetic venv creation failed'
    $env:OBS_TEST_REPO=$repo; $env:OBS_TEST_CASE='venv-handoff'
    $root=Join-Path $scratch 'venv-handoff';New-Item -ItemType Directory $root | Out-Null
    $result=Invoke-ReadonlyObservation -Python (Join-Path $venv 'Scripts/python.exe') -Operator $stub -Root $root -ExpectedCommit ('a'*40)
    Check ($result -eq 0) 'Actual PowerShell/venv controller handoff failed'
    $passed++
    foreach ($case in @('prepare-failure','prepare-late','prepare-stuck','package-late')) {
        $env:OBS_TEST_CASE=$case
        $root=Join-Path $scratch $case;New-Item -ItemType Directory $root | Out-Null
        $failed=$false
        try { $code=Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40) -PreparationSeconds $(if ($case -eq 'package-late') {150} else {.2}) -PackageSeconds .2 -StopSeconds .3 } catch { $failed=$true }
        $phases=Get-Content (Join-Path $root 'e/phases')
        if ($case -eq 'package-late') {
            Check (!($phases -contains 'seal')) 'Late packaging was sealed'
        } else { Check (!($phases -contains 'preflight')) 'Failed/unknown preparation admitted preflight' }
        Check ($failed -or $code -ne 0) 'Invalid preparation/package accepted'
        if ($case -eq 'prepare-stuck') { Stop-Process -Id ([int](Get-Content (Join-Path $root 'e/pid'))) -ErrorAction SilentlyContinue }
        $passed++
    }
    $env:OBS_TEST_CASE='cache-unowned';$root=Join-Path $scratch 'cache-unowned'
    New-Item -ItemType Directory $root | Out-Null
    $code=Invoke-ReadonlyObservation -Python $Python -Operator $stub -Root $root -ExpectedCommit ('a'*40)
    $phases=Get-Content (Join-Path $root 'e/phases')
    Check ($code -ne 0 -and !(($phases -contains 'observe') -or ($phases -contains 'package') -or ($phases -contains 'seal'))) 'Unknown cache cleanup progressed'
    $passed++
    # Literal150s boundary proof without waiting150s; OS exit remains authority.
    $start=[datetime]::UtcNow;$deadline=$start.AddSeconds(150)
    Check (!(Test-ObservationExitDeadline $deadline ($deadline.AddTicks(1)))) 'New150s budget accepted late zero exit'
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
    $prepared=& (Join-Path $repo 'docs\ross\PR1108_NATURAL_READONLY_ACCEPTANCE.ps1') -ExpectedCommit $localHead -Python $Python -SourceCheckout $source -BaseDirectory $prepBase -RuntimeSeconds 900 6>&1
    Check ($LASTEXITCODE -eq 361) 'Caller-local status was unexpectedly changed.'
    $preparedRoot=Get-ChildItem -Directory $prepBase | Where-Object { $_.Name -like 'ro-*' } | Select-Object -First 1
    Check ($null -ne $preparedRoot) 'Preparation did not create worktree.'
    $checkout=Join-Path $preparedRoot.FullName 's'
    Check (Test-Path -LiteralPath (Join-Path $checkout '.git') -PathType Leaf) 'Expected shared Git worktree, not full clone.'
    Check (!(Test-Path (Join-Path $preparedRoot.FullName 'e'))) 'Preparation launched preflight/runtime.'
    Check ((Get-Content -Raw (Join-Path $source 'sentinel.txt')) -match 'dirty source retained') 'Source changed.'
    Check ((Get-Content -Raw (Join-Path $old 'receipt.txt')) -match 'KEEP') 'Existing evidence changed.'
    Check (($prepared | Out-String) -match 'run_natural_readonly_observation.ps1') 'No separate execution command printed.'
    Check (($prepared | Out-String) -match '-RuntimeSeconds 900') 'Prepared command lost selected duration.'
    & git -C $source worktree remove --force $checkout
    Check ($global:LASTEXITCODE -eq 0) 'Synthetic worktree cleanup failed.'
    $passed++
    # Exercise the released preflight-only runner with a stub operator. Even
    # PASS must produce exactly one phase, and a failed preflight stays failed.
    $preflightScripts = Join-Path $scratch 'preflight-only-scripts'
    New-Item -ItemType Directory $preflightScripts | Out-Null
    foreach ($name in @('run_natural_readonly_preflight.ps1','Invoke-ReadonlyObservation.ps1')) {
        Copy-Item (Join-Path $repo ('scripts\certification\'+$name)) $preflightScripts
    }
    Copy-Item $stub (Join-Path $preflightScripts 'natural_readonly_operator.py')
    foreach ($case in @('success','preflight')) {
        $env:OBS_TEST_CASE = $case
        $onlyRoot = Join-Path $scratch ('preflight-only-'+$case)
        New-Item -ItemType Directory $onlyRoot | Out-Null
        $onlyChild = Invoke-ObservationChild -Python (Get-Command powershell.exe).Source -ChildArguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $preflightScripts 'run_natural_readonly_preflight.ps1'),'-Python',$Python,'-Root',$onlyRoot,'-ExpectedCommit',('a'*40)) -LogPrefix (Join-Path $scratch ('only-entry-'+$case)) -BudgetSeconds 20
        $onlyExit = $onlyChild.ExitCode
        Check ($onlyExit -eq $(if ($case -eq 'success') { 0 } else { 1 })) "Preflight-only $case exit propagation failed: actual $onlyExit"
        Check (((Get-Content (Join-Path $onlyRoot 'e\phases')) -join ',') -ceq 'prepare,preflight') 'Preflight-only runner continued beyond preflight'
        $onlyStatus = Get-Content (Join-Path $onlyRoot 'e\preflight-only-status.json') -Raw | ConvertFrom-Json
        Check (!$onlyStatus.observation_attempted -and !$onlyStatus.PAPER_READY) 'Preflight-only authority changed'
        $passed++
    }
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
