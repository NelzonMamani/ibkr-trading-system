# Run only on Windows CI. The release files are parsed and hashed, never invoked.
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or
    $PSVersionTable.PSVersion.Minor -ne 1) {
    throw 'Windows PowerShell 5.1 is required.'
}
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$schedulerName = 'SCHEDULE_REVIEWED_BENCHMARK_DRAFT.ps1'
$helperName = 'PREPARE_READ_ONLY_BENCHMARK_CAPTURE.ps1'
$callerName = 'READ_ONLY_BENCHMARK_CAPTURE_REQUIRED.ps1'
$root = Join-Path $env:RUNNER_TEMP ('ps-scheduler-' + [guid]::NewGuid().ToString('N'))
$evidence = Join-Path $root 'evidence with spaces'
$release = Join-Path $evidence 'ScheduledBenchmark\release'
$null = New-Item -ItemType Directory -Path $release -Force

function Assert-True($Condition, [string]$Message) {
    if (!$Condition) { throw $Message }
}

function Assert-Refuses([scriptblock]$Command, [string]$Message) {
    $failure = $null
    try { & $Command | Out-Null } catch { $failure = $_.Exception.Message }
    if ($null -eq $failure -or !$failure.Contains($Message)) {
        throw "Expected refusal '$Message'. Received '$failure'."
    }
}

function Assert-Parses([string]$Path) {
    $tokens = $null
    $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    Assert-True ($errors.Count -eq 0) ("Native parser errors in " + $Path + ": " + ($errors -join '; '))
}

function Replace-Only([string]$Text, [string]$Old, [string]$New, [int]$Expected = 1) {
    $count = [regex]::Matches($Text, [regex]::Escape($Old)).Count
    Assert-True ($count -eq $Expected) "Unexpected scheduler source occurrences ($count) for '$Old'."
    return $Text.Replace($Old, $New)
}

# Materialize repository blobs directly to preserve the pinned bytes even
# when the Windows checkout has CRLF conversion enabled.
$python = (Get-Command python.exe -ErrorAction Stop).Source
$copyBlob = 'import pathlib, subprocess, sys; pathlib.Path(sys.argv[3]).write_bytes(subprocess.check_output([''git'', ''-C'', sys.argv[1], ''show'', ''HEAD:docs/ross/'' + sys.argv[2]]))'
$scheduler = Join-Path $root $schedulerName
foreach ($name in @($schedulerName, $helperName, $callerName)) {
    $destination = if ($name -eq $schedulerName) { $scheduler } else { Join-Path $release $name }
    & $python -c $copyBlob $repo $name $destination
    if ($LASTEXITCODE -ne 0) { throw "Git blob staging failed for $name." }
    Assert-Parses $destination
}

$preview = (& $scheduler 6>&1 | Out-String)
Assert-True ($preview.Contains('Scheduler disabled') -and $preview.Contains('Nothing registered')) 'Default mode failed preview.'
Assert-Refuses { & $scheduler -Mode Install -ScheduledDate '2026-11-18' } 'DRAFT DISABLED'
Assert-Refuses { & $scheduler -Mode Run -ScheduledDate '2026-11-18' } 'DRAFT DISABLED'

# The exact delivered script above stays disabled. Only the temporary fixture
# uses an enabled release, a deterministic clock, and named test substitutes.
# Definition, trigger, principal and settings come from native cmdlets.
$text = [IO.File]::ReadAllText($scheduler)
$text = Replace-Only $text 'Enabled = $false' 'Enabled = $true'
$text = Replace-Only $text '$evidenceBase = ''C:\Users\nelzo\RossObservationEvidence''' '$evidenceBase = $fixture.Evidence'
$text = Replace-Only $text '[datetime]::UtcNow' '($fixture.Clock)' 6
$text = Replace-Only $text 'Get-ScheduledTask -TaskPath' 'Get-FixtureScheduledTask -TaskPath'
$text = Replace-Only $text 'Register-ScheduledTask -TaskName' 'Save-FixtureScheduledTask -TaskName'
$text = Replace-Only $text '& (Join-Path $releaseDirectory ''PREPARE_READ_ONLY_BENCHMARK_CAPTURE.ps1'')' 'Invoke-FixtureHelper'
$text = Replace-Only $text '& (Join-Path $releaseDirectory ''READ_ONLY_BENCHMARK_CAPTURE_REQUIRED.ps1'')' 'Invoke-FixtureCaller'
Assert-True ($text -notmatch '(?m)\bRegister-ScheduledTask\b|^\s*&\s*\(Join-Path \$releaseDirectory') 'Real task registration or release execution is reachable.'
$testPath = Join-Path $root 'scheduler fixture.ps1'
[IO.File]::WriteAllText($testPath, $text, [Text.Encoding]::ASCII)
Assert-Parses $testPath

$fixture = @{
    Evidence = $evidence
    Clock = [datetime]::new(2026, 11, 18, 14, 45, 0, [DateTimeKind]::Utc)
    Task = $null
    TaskName = $null
    Registrations = 0
    Helper = 0
    Caller = 0
}
function Save-FixtureScheduledTask {
    [CmdletBinding()]
    param($TaskName, $TaskPath, $InputObject)
    Assert-True ($TaskPath -ceq '\') 'Unexpected task path.'
    $fixture.Registrations++
    $fixture.Task = $InputObject
    $fixture.TaskName = $TaskName
}
function Get-FixtureScheduledTask {
    param($TaskPath)
    if ($fixture.TaskName) { [pscustomobject]@{ TaskName = $fixture.TaskName } }
}
function Invoke-FixtureHelper { $fixture.Helper++ }
function Invoke-FixtureCaller { $fixture.Caller++ }

$day = '2026-11-18'
$target = [datetime]::new(2026, 11, 18, 14, 55, 0, [DateTimeKind]::Utc)
Assert-Refuses { & $testPath -Mode Install -ScheduledDate '2026-11-26' } 'Choose one explicitly covered date'
$fixture.Clock = $target.AddMinutes(-5)
Assert-Refuses { & $testPath -Mode Install -ScheduledDate $day } 'Choose a future covered date'
$fixture.Clock = $target.AddMinutes(-10)
& $testPath -Mode Install -ScheduledDate $day
Assert-True ($fixture.Registrations -eq 1 -and $fixture.TaskName -ceq 'Ross-Benchmark-Once-20261118') 'Unexpected task identity.'
Assert-Refuses { & $testPath -Mode Install -ScheduledDate $day } 'A task for this profile/date already exists'
$task = $fixture.Task
$action = @($task.Actions)[0]
$trigger = @($task.Triggers)[0]
$boundary = [datetime]::Parse($trigger.StartBoundary, [Globalization.CultureInfo]::InvariantCulture).ToUniversalTime()
Assert-True ($boundary -eq $target) 'Wrong London to UTC to local trigger conversion.'
Assert-True (@($task.Triggers).Count -eq 1 -and
    ($null -eq $trigger.Repetition -or !$trigger.Repetition.Interval)) 'Task repeats.'
Assert-True ($task.Principal.LogonType.ToString() -eq 'Interactive' -and
    $task.Principal.RunLevel.ToString() -eq 'Limited') 'Principal must be interactive and limited.'
Assert-True (!$task.Settings.StartWhenAvailable -and !$task.Settings.WakeToRun -and
    !$task.Settings.AllowHardTerminate -and $task.Settings.RestartCount -eq 0 -and
    $task.Settings.MultipleInstances.ToString() -eq 'IgnoreNew') 'Unexpected task settings.'
$installed = Join-Path $action.WorkingDirectory 'SCHEDULE_REVIEWED_BENCHMARK.ps1'
$hash = (Get-FileHash -LiteralPath $installed).Hash.ToLowerInvariant()
$expected = '-NoLogo -NoProfile -File "{0}" -Mode Run -ScheduledDate {1} -ExpectedWrapperHash {2}' -f $installed, $day, $hash
Assert-True ($action.Execute -ceq (Join-Path $PSHOME 'powershell.exe') -and
    $action.Arguments -ceq $expected -and $installed.Contains(' ')) 'Task action quoting or execution-policy arguments changed.'

$fixture.Clock = $target.AddSeconds(-1)
Assert-Refuses { & $installed -Mode Run -ScheduledDate $day -ExpectedWrapperHash $hash } 'Outside this scheduled entry window'
$fixture.Clock = $target.AddMinutes(5)
Assert-Refuses { & $installed -Mode Run -ScheduledDate $day -ExpectedWrapperHash $hash } 'Outside this scheduled entry window'
Assert-True (!(Test-Path (Join-Path $action.WorkingDirectory 'attempt.started'))) 'Missed window consumed attempt.'
$fixture.Clock = $target
Assert-Refuses { & $installed -Mode Run -ScheduledDate $day -ExpectedWrapperHash ('0' * 64) } 'Installed wrapper identity differs'
foreach ($name in @($helperName, $callerName)) {
    $file = Join-Path $release $name
    $original = [IO.File]::ReadAllBytes($file)
    $changed = [byte[]]$original.Clone()
    $changed[0] = $changed[0] -bxor 1
    [IO.File]::WriteAllBytes($file, $changed)
    Assert-Refuses { & $installed -Mode Run -ScheduledDate $day -ExpectedWrapperHash $hash } 'A staged reviewed delivery file differs'
    [IO.File]::WriteAllBytes($file, $original)
}
Assert-True ($fixture.Helper -eq 0 -and $fixture.Caller -eq 0) 'A refused attempt invoked a substitute.'
& $installed -Mode Run -ScheduledDate $day -ExpectedWrapperHash $hash
$marker = Join-Path $action.WorkingDirectory 'attempt.started'
Assert-True (Test-Path -LiteralPath $marker -PathType Leaf) 'Single-use marker missing.'
try {
    & $installed -Mode Run -ScheduledDate $day -ExpectedWrapperHash $hash
    throw 'Repeat run unexpectedly returned.'
} catch {
    if ($_.Exception.InnerException -isnot [IO.IOException] -and $_.Exception -isnot [IO.IOException]) { throw }
}
Assert-True ($fixture.Helper -eq 1 -and $fixture.Caller -eq 1 -and $fixture.Registrations -eq 1) 'Duplicate reached a substitute.'
[ordered]@{
    status = 'PASS'
    scheduler_sha256 = (Get-FileHash -LiteralPath $scheduler).Hash.ToLowerInvariant()
    shell = $PSVersionTable.PSVersion.ToString()
    windows_zone = [TimeZoneInfo]::Local.Id
    trigger_utc = $boundary.ToString('o')
    checks = @('native_parse_all_three', 'default_and_disabled', 'native_task_definition',
        'london_time_conversion', 'quoted_action', 'early_and_missed_window', 'duplicate_install_and_attempt',
        'wrapper_hash_and_both_release_hashes')
    registration = 'SUBSTITUTE_ONLY'
    helper_and_caller = 'SUBSTITUTES_ONLY'
    laptop_staging = 'UNVERIFIED'
    prompt_visibility = 'UNVERIFIED'
    PAPER_READY = $false
    PAPER_READINESS_GATE = 'FAIL'
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'scheduler-validation.json') -Encoding UTF8
Write-Host 'Disabled scheduler Windows controls passed.'
