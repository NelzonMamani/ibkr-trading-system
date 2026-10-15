# Small controlled processes only; never the repository's full pytest suite.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Python)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSEdition -ne 'Desktop') {
    throw 'This regression must run in actual Windows PowerShell (powershell.exe).'
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'scripts\certification\Invoke-LoggedNativeProcess.ps1')
$shellPath = (Get-Command powershell.exe -CommandType Application).Source
$tempRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$scratch = Join-Path $tempRoot ('ps-status-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $scratch | Out-Null
$passed = 0
function Check($condition, $message) { if (!$condition) { throw $message } }
function Native($file, $arguments, $log) {
    Invoke-LoggedNativeProcess -FilePath $file -ArgumentList $arguments -LogPath $log
}
function Fixture($name, $testSource) {
    $fixtureRoot = Join-Path $scratch ("fixture 'quoted' " + $name)
    $scripts = Join-Path $fixtureRoot 'scripts\certification'
    $offline = Join-Path $fixtureRoot 'tests\offline'
    New-Item -ItemType Directory $scripts,$offline | Out-Null
    foreach ($file in @('verify_natural_readonly_offline.ps1','invoke_natural_readonly_offline.ps1','Invoke-LoggedNativeProcess.ps1')) {
        Copy-Item (Join-Path $repo "scripts\certification\$file") $scripts
    }
    Copy-Item (Join-Path $repo 'tests\offline\sitecustomize.py') $offline
    $testSource | Set-Content -Encoding ascii (Join-Path $fixtureRoot 'tests\test_controlled.py')
    "__pycache__/`n.pytest_cache/" | Set-Content -Encoding ascii (Join-Path $fixtureRoot '.gitignore')
    & git -C $fixtureRoot init -q
    Check ($LASTEXITCODE -eq 0) 'Fixture git init failed.'
    & git -C $fixtureRoot add .
    Check ($LASTEXITCODE -eq 0) 'Fixture git add failed.'
    & git -C $fixtureRoot -c user.name=Harness -c user.email=harness@example.invalid commit -qm fixture
    Check ($LASTEXITCODE -eq 0) 'Fixture commit failed.'
    $head = (& git -C $fixtureRoot rev-parse HEAD | Out-String).Trim()
    Check ($LASTEXITCODE -eq 0) 'Fixture head failed.'
    [pscustomobject]@{ Root=$fixtureRoot; Scripts=$scripts; Head=$head }
}
try {
    foreach ($script in @('scripts\certification\Invoke-LoggedNativeProcess.ps1',
        'scripts\certification\invoke_natural_readonly_offline.ps1',
        'docs\ross\PR1108_NATURAL_READONLY_ACCEPTANCE.ps1')) {
        $parseErrors = $null; $tokens = $null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $repo $script), [ref]$tokens, [ref]$parseErrors)
        Check ($parseErrors.Count -eq 0) "PowerShell parse error: $script"
    }
    $passed++
    # Match the user's interactive & { local sentinel; native | Tee } launch in
    # a separate -Command shell. Compare its local/global statuses to a retained
    # Process.ExitCode; no inference from a pytest-looking output line.
    $successChild = Join-Path $scratch 'success.ps1'
    "& '$($Python.Replace("'","''"))' -c 'import sys; sys.exit(0)'" | Set-Content $successChild
    $reproFile = Join-Path $scratch 'old-pipeline.json'
    $reproLog = Join-Path $scratch 'old-pipeline.log'
    $repro = @'
& {
    $LASTEXITCODE = 1
    & __SHELL__ -NoProfile -File __CHILD__ 2>&1 | Tee-Object -FilePath __LOG__ -ErrorAction Stop
    [pscustomobject]@{ reported=$LASTEXITCODE; global=$global:LASTEXITCODE; local=(Get-Variable LASTEXITCODE -Scope Local).Value } | ConvertTo-Json | Set-Content __RESULT__
}
'@
    foreach ($pair in @(@('__SHELL__',$shellPath),@('__CHILD__',$successChild),@('__LOG__',$reproLog),@('__RESULT__',$reproFile))) {
        $repro = $repro.Replace($pair[0], "'" + $pair[1].Replace("'","''") + "'")
    }
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($repro))
    $result = Native $shellPath @('-NoProfile','-EncodedCommand',$encoded) (Join-Path $scratch 'old-shell.log')
    Check ($result.ExitCode -eq 0) 'Controlled successful shell unexpectedly failed.'
    $old = Get-Content -Raw $reproFile | ConvertFrom-Json
    Write-Host ('OLD_PIPELINE: ' + ($old | ConvertTo-Json -Compress))
    Check ($old.reported -eq 1 -and $old.global -eq 0) 'Expected local sentinel/global child-status shadowing did not reproduce.'
    $passed++

    foreach ($case in @(
        @{Name='success'; Source='def test_ok(): assert True'; Code=0; Marker='1 passed'},
        @{Name='failure'; Source='def test_bad(): assert False'; Code=1; Marker='1 failed'},
        @{Name='collection'; Source='raise RuntimeError("controlled collection failure")'; Code=2; Marker='1 error'}
    )) {
        $fixture = Fixture $case.Name $case.Source
        foreach ($entry in @('verify_natural_readonly_offline.ps1','invoke_natural_readonly_offline.ps1')) {
            $arguments = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
                (Join-Path $fixture.Scripts $entry),'-ExpectedCommit',$fixture.Head,'-Python',$Python)
            $innerLog = Join-Path $scratch ($case.Name + '-inner.log')
            if ($entry -eq 'invoke_natural_readonly_offline.ps1') { $arguments += @('-LogPath',$innerLog) }
            $result = Native $shellPath $arguments (Join-Path $scratch ($case.Name+'-'+$entry+'.log'))
            Check ($result.ExitCode -eq $case.Code) "$entry did not preserve $($case.Name) exit $($case.Code)."
            Check ((Get-Content -Raw $result.LogPath) -match [regex]::Escape($case.Marker)) 'Controlled pytest result missing.'
            if ($entry -eq 'invoke_natural_readonly_offline.ps1') {
                Check ((Get-Content -Raw $innerLog) -match [regex]::Escape($case.Marker)) 'Verification log lost child output.'
            }
            $passed++
        }
    }
    $missingPython = Join-Path $scratch 'absent-python.exe'
    $result = Native $shellPath @('-NoProfile','-File',(Join-Path $fixture.Scripts 'invoke_natural_readonly_offline.ps1'),
        '-ExpectedCommit',$fixture.Head,'-Python',$missingPython,'-LogPath',(Join-Path $scratch 'missing-python.log')) (Join-Path $scratch 'launch-wrapper.log')
    Check ($result.ExitCode -ne 0) 'Missing Python reported success.'
    $passed++
    $failed = $false
    try { $null = Native $missingPython @() (Join-Path $scratch 'launch.log') } catch { $failed = $true }
    Check $failed 'Process launch failure reported success.'
    $passed++

    $sentinel = Join-Path $scratch 'must-not-start'
    $failed = $false
    try { $null = Native $Python @('-c',"open(r'$sentinel','w').write('bad')") $scratch } catch { $failed = $true }
    Check ($failed -and !(Test-Path $sentinel)) 'Log-open error launched child or reported success.'
    $passed++

    # Deterministic post-exit log-write failure, without filling a real disk.
    class BrokenLogWriter {
        [void] Write([string]$text) { throw [IO.IOException]::new('controlled log-write error') }
        [void] Flush() {}
        [void] Dispose() {}
    }
    function New-Object {
        param([string]$TypeName, [object[]]$ArgumentList)
        if ($TypeName -eq 'System.IO.StreamWriter') { return [BrokenLogWriter]::new() }
        Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList
    }
    try {
        $failed = $false; $childCode = $null
        try { $null = Native $Python @('-c','print("controlled success")') (Join-Path $scratch 'write-error.log') }
        catch { $failed = $true; $childCode = $_.Exception.Data['ChildExitCode'] }
        Check ($failed -and $childCode -eq 0) 'Log-write error lost successful child status or reported wrapper success.'
        $passed++
    } finally { Remove-Item Function:\New-Object }

    # Drain a pipe-sized payload on BOTH streams, preserve quoted arguments and
    # a nonstandard native status; success on stderr is not itself failure.
    $result = Native $Python @('-c','import sys; print(sys.argv[1]); sys.stdout.write("x"*100000); sys.stderr.write("y"*100000); sys.exit(7)', 'a "quoted" value\') (Join-Path $scratch 'pipes.log') 6>$null
    Check ($result.ExitCode -eq 7) 'Native status7 was remapped.'
    Check ((Get-Item $result.LogPath).Length -gt 200000) 'Pipe output lost.'
    Check ((Get-Content -Raw $result.LogPath).StartsWith('a "quoted" value\')) 'Windows argument quoting changed input.'
    $passed++
    Write-Host "WINDOWS_POWERSHELL_HARNESS: $passed controlled checks passed; $($PSVersionTable.PSVersion); logs=$scratch"
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    Write-Host "HARNESS FAILURE: completed=$passed; logs=$scratch"
    exit 1
}
