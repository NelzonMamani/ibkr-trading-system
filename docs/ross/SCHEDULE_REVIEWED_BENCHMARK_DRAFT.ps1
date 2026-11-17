# DRAFT: disabled pending native Windows validation.
# Windows PowerShell 5.1 Desktop, under the current execution policy.
# Default Preview makes no changes. This file has not been tested on Windows.
#
# The release below is bound to the immutable PR1236 delivery.
# Keep disabled pending native Windows 5.1 parsing, task-definition validation
# and confirmation that the operator prompt is accessible in the task session.
# Preview performs no installation, capture, or release-file execution.
[CmdletBinding()]
param(
    [ValidateSet('Preview', 'Install', 'Run')][string]$Mode = 'Preview',
    [string]$ScheduledDate = '',
    [string]$ExpectedWrapperHash = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$evidenceBase = 'C:\Users\nelzo\RossObservationEvidence'
$releaseDirectory = Join-Path $evidenceBase 'ScheduledBenchmark\release'
$reviewedDates = @('2026-11-17','2026-11-18','2026-11-19','2026-11-20',
                  '2026-11-23','2026-11-24','2026-11-25','2026-11-27','2026-11-30')
# This list only restricts scheduling. The maintained owner must independently
# admit the actual calendar, session, full envelope, account and exact client71.
$release = @{
    Enabled = $false
    DeliveryCommit = 'a427f887c9cf93f72dbc218d786d4bb44b0fcfdc'
    SourceCommit = 'b0ec1bf606a676fa5ca55847c3eba4278a582a1e'
    SourceTree = '0ba25fef228e496c22897f2873e18a6bf6123478'
    Files = @(
        @{ Name = 'PREPARE_READ_ONLY_BENCHMARK_CAPTURE.ps1'; Bytes = 6865; SHA256 = '1e36253808f194a036bd50a10f1fb02251239f3e2c62ea3186814fde963f4938' },
        @{ Name = 'READ_ONLY_BENCHMARK_CAPTURE_REQUIRED.ps1'; Bytes = 30971; SHA256 = '5c84ca6272d05fdc42f2c66d71b47ab566d70698f5532d46c4010e80eadf93d5' }
    )
}

function Assert-OrdinaryLocalPath {
    param([string]$Path, [switch]$File)
    if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Contains('"')) {
        throw 'An explicit ordinary local Windows path is required.'
    }
    $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($Path))
    if ($drive.DriveType -ne [IO.DriveType]::Fixed) { throw 'A local fixed drive is required.' }
    # Inspect ancestry root-first, before accessing any descendant.
    $nodes = @(); $current = $Path
    while (![string]::IsNullOrEmpty($current)) {
        $nodes = @($current) + $nodes
        $parent = Split-Path -Path $current -Parent
        if ([string]::IsNullOrEmpty($parent) -or $parent -eq $current) { break }
        $current = $parent
    }
    for ($index = 0; $index -lt $nodes.Count; $index++) {
        $node = Get-Item -LiteralPath $nodes[$index] -Force -ErrorAction Stop
        if ($node.PSProvider.Name -ne 'FileSystem' -or
            ($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The selected path or ancestry is not ordinary local storage.'
        }
        $leafFile = $File -and $index -eq ($nodes.Count - 1)
        if (($leafFile -and $node.PSIsContainer) -or (!$leafFile -and !$node.PSIsContainer)) {
            throw 'Unexpected file or directory in the selected path.'
        }
    }
}

function Assert-ReviewedRelease {
    if ($release.Enabled -ne $true) {
        throw 'DRAFT DISABLED: native Windows validation and separate activation are pending.'
    }
    foreach ($key in @('DeliveryCommit','SourceCommit','SourceTree')) {
        if ($release[$key] -cnotmatch '^[0-9a-f]{40}$') { throw 'Reviewed release identity is incomplete.' }
    }
    if ($release.SourceCommit -eq '0a9e76d54267f8b0512cb352ec01dae5cfb9cf72') {
        throw 'The unrepaired PR1235 capture release is not admitted.'
    }
    Assert-OrdinaryLocalPath -Path $releaseDirectory
    foreach ($file in $release.Files) {
        if ($file.Bytes -le 0 -or $file.SHA256 -cnotmatch '^[0-9a-f]{64}$') {
            throw 'Reviewed delivery size or hash is incomplete.'
        }
        $path = Join-Path $releaseDirectory $file.Name
        Assert-OrdinaryLocalPath -Path $path -File
        if ((Get-Item -LiteralPath $path).Length -ne $file.Bytes -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.SHA256) {
            throw 'A staged reviewed delivery file differs; nothing launched.'
        }
        $tokens = $null; $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$parseErrors) | Out-Null
        if (@($parseErrors).Count -ne 0) { throw 'Native parsing failed for a reviewed delivery file.' }
    }
}

function Get-TargetUtc {
    if ($reviewedDates -cnotcontains $ScheduledDate) {
        throw 'Choose one explicitly covered date from 17 to 30 November 2026.'
    }
    $wall = [datetime]::ParseExact(($ScheduledDate + ' 14:55:00'), 'yyyy-MM-dd HH:mm:ss',
        [Globalization.CultureInfo]::InvariantCulture)
    $wall = [datetime]::SpecifyKind($wall, [DateTimeKind]::Unspecified)
    $zone = [TimeZoneInfo]::FindSystemTimeZoneById('GMT Standard Time')
    return [TimeZoneInfo]::ConvertTimeToUtc($wall, $zone)
}

if ($Mode -eq 'Preview') {
    Write-Host 'DRAFT: one benchmark capture launch at 14:55 Europe/London on one chosen covered date.'
    Write-Host 'PR1236 release pinned. Scheduler disabled pending native Windows validation.'
    Write-Host 'Uses existing confirmed paths, fresh roots and the maintained operator confirmation.'
    Write-Host 'Requires the logged-in user, awake laptop and existing PAPER/Read-Only TWS session.'
    Write-Host 'Nothing registered, downloaded, connected or launched. PAPER_READY=NO.'
    return
}

if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSEdition -ne 'Desktop' -or
    $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
    throw 'Use Windows PowerShell 5.1 Desktop under the current execution policy.'
}
if ($release.Enabled -ne $true) {
    throw 'DRAFT DISABLED: native Windows validation and separate activation are pending.'
}

if ($Mode -eq 'Install') {
    Assert-ReviewedRelease
    $targetUtc = Get-TargetUtc
    $taskName = 'Ross-Benchmark-Once-' + $ScheduledDate.Replace('-', '')
    if ($targetUtc -le [datetime]::UtcNow.AddMinutes(5)) { throw 'Choose a future covered date; no catch-up launch.' }
    Assert-OrdinaryLocalPath -Path $evidenceBase
    Assert-OrdinaryLocalPath -Path $PSCommandPath -File
    Import-Module ScheduledTasks -ErrorAction Stop
    if (@(Get-ScheduledTask -TaskPath '\' | Where-Object { $_.TaskName -ceq $taskName }).Count -ne 0) {
        throw 'A task for this profile/date already exists. Nothing overwritten or rescheduled.'
    }
    $installDir = Join-Path $evidenceBase ('benchmark-schedule-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $installDir -ErrorAction Stop | Out-Null
    $installedScript = Join-Path $installDir 'SCHEDULE_REVIEWED_BENCHMARK.ps1'
    $selfHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $inputStream = [IO.File]::OpenRead($PSCommandPath)
    try {
        $outputStream = [IO.File]::Open($installedScript, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
    } finally { $inputStream.Dispose() }
    if ((Get-FileHash -LiteralPath $installedScript -Algorithm SHA256).Hash.ToLowerInvariant() -cne $selfHash) {
        throw 'Installed wrapper differs; preserve folder, no registration.'
    }
    $powershell = Join-Path $PSHOME 'powershell.exe'
    $arguments = '-NoLogo -NoProfile -File "{0}" -Mode Run -ScheduledDate {1} -ExpectedWrapperHash {2}' -f
        $installedScript, $ScheduledDate, $selfHash
    $action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $installDir
    $trigger = New-ScheduledTaskTrigger -Once -At ($targetUtc.ToLocalTime())
    $userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $principal = New-ScheduledTaskPrincipal -UserId $userSid -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([timespan]::Zero) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $settings.StartWhenAvailable = $false
    $settings.RestartCount = 0
    $settings.WakeToRun = $false
    $settings.AllowHardTerminate = $false
    $definition = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description 'One reviewed READ_ONLY benchmark launch; real operator confirmation and maintained admission required.'
    Register-ScheduledTask -TaskName $taskName -TaskPath '\' -InputObject $definition -ErrorAction Stop | Out-Null
    Write-Host ('Registered ' + $taskName + ' for 14:55 UK. Keep the laptop awake and be present for confirmation.')
    Write-Host ('Wrapper folder retained: ' + $installDir)
    return
}

# Verify the installed snapshot and local result destination before any writes.
Assert-OrdinaryLocalPath -Path $PSCommandPath -File
if ($ExpectedWrapperHash -cnotmatch '^[0-9a-f]{64}$' -or
    (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedWrapperHash) {
    throw 'Installed wrapper identity differs; nothing launched.'
}
Assert-OrdinaryLocalPath -Path $PSScriptRoot
$wrapperResult = @{
    scheduled_date = $ScheduledDate; stage = 'wrapper_admission'; status = 'STARTED'
    started_utc = [datetime]::UtcNow.ToString('o'); finished_utc = $null
    error_type = $null; PAPER_READY = $false; PAPER_READINESS_GATE = 'FAIL'
    receipt_scope = 'Wrapper invocation only; maintained receipts own observation and safety outcomes.'
}
try {
    Assert-ReviewedRelease
    $targetUtc = Get-TargetUtc
    # This is the scheduled entry window. Actual capture admission is still
    # bounded separately by the maintained caller after operator confirmation.
    if ([datetime]::UtcNow -lt $targetUtc -or [datetime]::UtcNow -ge $targetUtc.AddMinutes(5)) {
        throw 'Outside this scheduled entry window. No catch-up, retry or observation.'
    }
    $startedMarker = Join-Path $PSScriptRoot 'attempt.started'
    $claim = [IO.File]::Open($startedMarker, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $claim.Dispose() # Retained on every outcome; this scheduled attempt is single-use.
    Write-Host 'One fresh benchmark attempt. Keep all other Ross/capture sessions stopped.'
    Write-Host 'Read the maintained PAPER/Read-Only confirmation carefully; it will not be filled automatically.'
    # Both files were checked before either executes. Existing owners retain
    # source-pin, process, calendar, privacy, client71, mutation and cleanup authority.
    $wrapperResult.stage = 'release_preparation'
    & (Join-Path $releaseDirectory 'PREPARE_READ_ONLY_BENCHMARK_CAPTURE.ps1')
    Assert-ReviewedRelease
    if ([datetime]::UtcNow -ge $targetUtc.AddMinutes(5)) { throw 'Preparation exceeded this launch window; preserve folder, no retry.' }
    $wrapperResult.stage = 'maintained_caller'
    & (Join-Path $releaseDirectory 'READ_ONLY_BENCHMARK_CAPTURE_REQUIRED.ps1')
    $wrapperResult.status = 'CALLER_RETURNED_REVIEW_MAINTAINED_RECEIPTS'
    Write-Host 'Maintained caller returned. Review its recorded outcome and evidence; this message is not an acceptance result.'
} catch {
    $wrapperResult.status = 'FAILED_PRESERVE_ALL_EVIDENCE'
    $wrapperResult.error_type = $_.Exception.GetType().Name
    throw
} finally {
    $wrapperResult.finished_utc = [datetime]::UtcNow.ToString('o')
    $resultPath = Join-Path $PSScriptRoot ('scheduled-wrapper-result-' + [guid]::NewGuid().ToString('N') + '.json')
    $wrapperResult | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host ('Wrapper result: ' + $resultPath)
    Write-Host 'PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.'
}
