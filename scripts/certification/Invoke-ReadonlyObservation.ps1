# Timeliness is proved by the OS exit timestamp, never by a child's PASS file.
function Test-ObservationExitDeadline {
    param([datetime]$DeadlineUtc, [Nullable[datetime]]$ExitUtc)
    return ($null -ne $ExitUtc -and $ExitUtc.ToUniversalTime() -le $DeadlineUtc)
}
# Generic process boundary: tests supply controlled children; released runner fixes the operator.
function Invoke-ObservationChild {
    param([string]$Python, [string[]]$ChildArguments, [string]$LogPrefix,
          [string]$StopPath, [double]$BudgetSeconds, [double]$StopSeconds = 30,
          [scriptblock]$LogStreamFactory = { param($path) [IO.File]::Open($path, 'Create', 'Write', 'Read') })
    $ErrorActionPreference = 'Stop'
    $process = $null; $outFile = $null; $errFile = $null
    $code = $null; $exited = $false; $timedOut = $false; $started = $false; $stopWaited = $false; $childError = $null
    $startUtc = $null; $deadlineUtc = $null; $exitUtc = $null; $clock = $null; $timeoutReason = $null
    try {
        # Open both logs before starting anything. Failures cannot launch a child.
        $outFile = & $LogStreamFactory ($LogPrefix + '.stdout.log')
        $errFile = & $LogStreamFactory ($LogPrefix + '.stderr.log')
        $info = New-Object Diagnostics.ProcessStartInfo
        $info.FileName = $Python
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $info.Arguments = (($ChildArguments | ForEach-Object {
            '"' + [regex]::Replace([regex]::Replace($_, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
        }) -join ' ')
        $process = New-Object Diagnostics.Process
        $process.StartInfo = $info
        $startUtc = [datetime]::UtcNow
        $deadlineUtc = $startUtc.AddSeconds($BudgetSeconds)
        $clock = [Diagnostics.Stopwatch]::StartNew()
        if (!$process.Start()) { throw 'Child launch failed.' }
        $started = $true
        $childId = $process.Id
        # Retain the handle before exit; never depend on scoped LASTEXITCODE.
        $null = $process.Handle
        $outCopy = $process.StandardOutput.BaseStream.CopyToAsync($outFile)
        $errCopy = $process.StandardError.BaseStream.CopyToAsync($errFile)
        while ($true) {
            $remaining = $BudgetSeconds - $clock.Elapsed.TotalSeconds
            $waitMs = [int][Math]::Max(0, [Math]::Min(200, [Math]::Ceiling($remaining * 1000)))
            $observedExit = $process.WaitForExit($waitMs)
            if ($observedExit) {
                try { $exitUtc = $process.ExitTime.ToUniversalTime() } catch { $exitUtc = $null }
                if (Test-ObservationExitDeadline -DeadlineUtc $deadlineUtc -ExitUtc $exitUtc) { break }
                $timedOut = $true
                $timeoutReason = if ($null -eq $exitUtc) { 'EXIT_TIME_UNVERIFIED' } else { 'OS_EXIT_AFTER_DEADLINE' }
                break
            }
            if ($outCopy.IsFaulted -or $errCopy.IsFaulted) { throw 'Child log write failed.' }
            if ($clock.Elapsed.TotalSeconds -ge $BudgetSeconds) {
                # Recheck a process that exited between the bounded wait and
                # deadline decision. A late observer may accept only proven timely exit.
                if ($process.WaitForExit(0)) {
                    try { $exitUtc = $process.ExitTime.ToUniversalTime() } catch { $exitUtc = $null }
                    if (Test-ObservationExitDeadline -DeadlineUtc $deadlineUtc -ExitUtc $exitUtc) { break }
                }
                $timedOut = $true
                $timeoutReason = 'ALIVE_AT_DEADLINE_OR_LATE_EXIT'
                if ($StopPath) {
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($StopPath)) | Out-Null
                    [IO.File]::WriteAllText($StopPath, "GRACEFUL_STOP_REQUESTED`n")
                }
                $stopWaited = $true
                if (!$process.WaitForExit([int]($StopSeconds * 1000))) {
                    throw "Child PID $childId exceeded stop budget. No broad kill; inspect retained process and evidence."
                }
                break
            }
            if (($clock.Elapsed.TotalSeconds % 5) -lt 0.21) {
                Write-Host ("Elapsed {0:N0}s; logs {1}.*.log; stop file {2}" -f $clock.Elapsed.TotalSeconds,$LogPrefix,$StopPath)
            }
        }
        $exited = $true
        $code = $process.ExitCode
        try { $exitUtc = $process.ExitTime.ToUniversalTime() } catch { }
        # Descendants holding a pipe cannot make cleanup wait indefinitely.
        if (!$outCopy.Wait(5000) -or !$errCopy.Wait(5000)) { throw 'Child pipes did not close within budget.' }
        $outFile.Flush(); $errFile.Flush()
        [pscustomobject]@{ ExitCode = $code; TimedOut = $timedOut; Exited = $true; ProcessId = $childId; StartedUtc = $startUtc; DeadlineUtc = $deadlineUtc; ExitUtc = $exitUtc; TimeoutReason = $timeoutReason }
    } catch {
        $childError = $_
        # Logging/control failures still request the same cooperative stop. Keep
        # the original error even if stop-file creation or waiting also fails.
        if ($started -and !$exited -and !$stopWaited) {
            try {
                if ($StopPath) {
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($StopPath)) | Out-Null
                    [IO.File]::WriteAllText($StopPath, "GRACEFUL_STOP_REQUESTED`n")
                }
                $stopWaited = $true
                $exited = $process.WaitForExit([int]($StopSeconds * 1000))
                if ($exited) { $code = $process.ExitCode }
            } catch { }
        }
        $childError.Exception.Data['ChildStarted'] = $started
        $childError.Exception.Data['ChildExitCode'] = $code
        $childError.Exception.Data['ChildExited'] = $exited
        throw $childError
    } finally {
        $disposeError = $null
        try {
            if ($exited -and $null -eq $exitUtc) {
                try { $exitUtc = $process.ExitTime.ToUniversalTime() } catch { }
            }
            [ordered]@{ started=$started; exited=$exited; exit_code=$code;
                timed_out=$timedOut; timeout_reason=$timeoutReason;
                budget_seconds=$BudgetSeconds; cleanup_budget_seconds=$StopSeconds;
                started_utc=$startUtc; deadline_utc=$deadlineUtc; os_exit_utc=$exitUtc;
                completed_utc=[datetime]::UtcNow;
                elapsed_seconds=$(if ($null -ne $clock) { $clock.Elapsed.TotalSeconds } else { $null });
                stop_waited=$stopWaited;
                timely_exit_verified=($exited -and !$timedOut -and (Test-ObservationExitDeadline -DeadlineUtc $deadlineUtc -ExitUtc $exitUtc))
            } | ConvertTo-Json | Set-Content -Encoding UTF8 ($LogPrefix + '.process.json')
        } catch { $disposeError = $_ }
        foreach ($owned in @($outFile,$errFile,$process)) {
            if ($null -ne $owned) {
                try { $owned.Dispose() } catch { if ($null -eq $disposeError) { $disposeError = $_ } }
            }
        }
        if ($null -eq $childError -and $null -ne $disposeError) {
            $disposeError.Exception.Data['ChildStarted'] = $started
            $disposeError.Exception.Data['ChildExited'] = $exited
            $disposeError.Exception.Data['ChildExitCode'] = $code
            throw $disposeError
        }
    }
}
function Invoke-ReadonlyObservation {
    param([string]$Python, [string]$Operator, [string]$Root, [string]$ExpectedCommit,
          [double]$PreflightSeconds = 150, [double]$ObservationSeconds = 540,
          [double]$StopSeconds = 30, [double]$PackageSeconds = 150,
          [double]$PreparationSeconds = 150, [double]$SealSeconds = 90,
          [ValidateRange(180,1800)][int]$RuntimeSeconds = 180, [switch]$PreflightOnly)
    $ErrorActionPreference = 'Stop'
    $durationArguments = @()
    if ($RuntimeSeconds -ne 180) { $durationArguments = @([string]$RuntimeSeconds) }
    $evidence = Join-Path $Root 'e'
    if (Test-Path -LiteralPath $evidence) { throw 'Evidence already exists; prepare a fresh run root. Existing evidence preserved.' }
    $preparation = Join-Path $Root 'preparation'
    if (Test-Path (Join-Path $Root 'runner.json')) { throw 'Runner already attempted; no reuse/resume.' }
    $oldToken = $env:READONLY_ADMISSION_TOKEN
    $env:READONLY_ADMISSION_TOKEN = [guid]::NewGuid().ToString('N')
    $runnerFile = [IO.File]::Open((Join-Path $Root 'runner.json'), 'CreateNew', 'Write', 'None')
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes((@{pid=$PID;token=$env:READONLY_ADMISSION_TOKEN;creation_token=('windows-filetime:'+[Diagnostics.Process]::GetCurrentProcess().StartTime.ToUniversalTime().ToFileTimeUtc())} | ConvertTo-Json))
        $runnerFile.Write($bytes,0,$bytes.Length)
    } finally { $runnerFile.Dispose() }
    [IO.Directory]::CreateDirectory($preparation) | Out-Null
    $stop = Join-Path $evidence 'terminal\STOP_REQUESTED'
    $result = 1; $canPackage = $true
    $phaseStatus = [ordered]@{ preparation_exit=$null; preparation_timed_out=$null; preflight_exit=$null; observation_exit=$null; package_exit=$null; final_exit=$null; package_status='NOT_STARTED' }
    try {
        $canPackage = $false
        $prepared = Invoke-ObservationChild -Python $Python -ChildArguments (@('-E','-u',$Operator,'prepare',$Root,$ExpectedCommit) + $durationArguments) -LogPrefix (Join-Path $preparation 'prepare-process') -StopPath (Join-Path $preparation 'STOP_REQUESTED') -BudgetSeconds $PreparationSeconds -StopSeconds $StopSeconds
        $phaseStatus.preparation_exit = $prepared.ExitCode
        $phaseStatus.preparation_timed_out = $prepared.TimedOut
        if ($prepared.ExitCode -ne 0 -or $prepared.TimedOut) { throw 'Filesystem preparation failed or late; no admission.' }
        [IO.Directory]::CreateDirectory($evidence) | Out-Null
        $preflight = Invoke-ObservationChild -Python $Python -ChildArguments (@('-E','-u',$Operator,'preflight',$Root,$ExpectedCommit) + $durationArguments) -LogPrefix (Join-Path $evidence 'preflight-process') -StopPath (Join-Path $evidence 'preflight.stop') -BudgetSeconds $PreflightSeconds -StopSeconds $StopSeconds
        $canPackage = $true
        $result = $preflight.ExitCode
        $phaseStatus.preflight_exit = $result
        $phaseStatus.preflight_timed_out = $preflight.TimedOut
        $phaseStatus.preflight_deadline_status = if ($preflight.TimedOut) { 'TIMEOUT' } else { 'TIMELY_EXIT_VERIFIED' }
        Write-Host "Preflight exit: $result"
        if ($result -ne 0) {
            $reasonFile = Join-Path $evidence 'preflight-result.json'
            if (Test-Path $reasonFile) {
                $reason = Get-Content -Raw $reasonFile | ConvertFrom-Json
                Write-Host ("Preflight failed at {0}: {1}" -f $reason.stage,$reason.reason)
            } else {
                Get-Content (Join-Path $evidence 'preflight-process.stderr.log') | ForEach-Object { Write-Host $_ }
            }
        }
        if ($preflight.TimedOut) { throw ('Preflight timed out; no observation launch. Child exit {0} is separate from deadline failure ({1}); see preflight-process.process.json.' -f $result,$preflight.TimeoutReason) }
        if ($result -eq 0 -and !$PreflightOnly) {
            Write-Host "Logs: $evidence\terminal\stdout.log and stderr.log"
            Write-Host "Early graceful stop: New-Item -ItemType File -Force '$stop'"
            try {
                $canPackage = $false
                $observed = Invoke-ObservationChild -Python $Python -ChildArguments (@('-E','-u',$Operator,'observe',$Root,$ExpectedCommit) + $durationArguments) -LogPrefix (Join-Path $evidence 'supervisor') -StopPath $stop -BudgetSeconds $ObservationSeconds -StopSeconds $StopSeconds
                $canPackage = $true
                $result = $observed.ExitCode
                $phaseStatus.observation_exit = $result
                if ($observed.TimedOut -and $result -eq 0) { $result = 124 }
            } catch {
                # Never package files while a supervisor may still own writers.
                $canPackage = $false
                throw
            }
        }
    } catch {
        if ($result -eq 0) { $result = 1 }
        $phaseStatus.outer_error = $_.Exception.GetType().Name
        $phaseStatus.outer_reason = $_.Exception.Message
        if ($_.Exception.Data.Contains('ChildStarted')) {
            $canPackage = $false
        }
        throw
    } finally {
        if (!(Test-Path $evidence)) { [IO.Directory]::CreateDirectory($evidence) | Out-Null }
        if ($canPackage -and !$PreflightOnly) {
            $phaseStatus.package_status = 'RUNNING'
            $phaseStatus | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'phase-status-before-package.json')
            try {
                $packaged = Invoke-ObservationChild -Python $Python -ChildArguments (@('-E','-u',$Operator,'package',$Root,$ExpectedCommit) + $durationArguments) -LogPrefix (Join-Path $evidence 'package-process') -StopPath (Join-Path $evidence 'package.stop') -BudgetSeconds $PackageSeconds -StopSeconds $StopSeconds
                $phaseStatus.package_exit = $packaged.ExitCode
                $phaseStatus.package_status = if ($packaged.TimedOut) { 'TIMEOUT' } elseif ($packaged.ExitCode -eq 0) { 'PASS' } elseif ($packaged.ExitCode -eq 2) { 'DIAGNOSTIC_ONLY' } else { 'NONZERO' }
                Write-Host ("Package exit: {0}; status: {1}" -f $packaged.ExitCode,$phaseStatus.package_status)

                if ($result -eq 0 -and ($packaged.ExitCode -ne 0 -or $packaged.TimedOut)) {
                    $result = if ($packaged.ExitCode -ne 0) { $packaged.ExitCode } else { 124 }
                }
            } catch {
                $phaseStatus.package_status = 'ERROR'
                $phaseStatus.package_exit = $_.Exception.Data['ChildExitCode']
                if ($result -eq 0) { $result = 1 }
                Write-Host ("Packaging failed: {0}; inspect {1}" -f $_.Exception.GetType().Name,$evidence)
            }
        }
        $phaseStatus.receipt_scope = 'Actual preflight/observation/package OS exits; filesystem-only sealing must pass before ZIP is announced.'
        $phaseStatus.final_exit = $result
        $phaseStatus | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'phase-status.json')
        $zip = Join-Path $Root 'ross-natural-readonly-upload.zip'
        if ($canPackage -and $phaseStatus.package_status -in @('PASS','DIAGNOSTIC_ONLY') -and $phaseStatus.package_exit -in @(0,2) -and (Test-Path -LiteralPath $zip -PathType Leaf)) {
            try {
                $sealed = Invoke-ObservationChild -Python $Python -ChildArguments (@('-E','-u',$Operator,'seal',$Root,$ExpectedCommit) + $durationArguments) -LogPrefix (Join-Path $Root 'seal-process') -StopPath (Join-Path $Root 'seal.stop') -BudgetSeconds $SealSeconds -StopSeconds $StopSeconds
                Write-Host ("Archive seal exit: {0}" -f $sealed.ExitCode)
                if ($sealed.ExitCode -eq 0 -and !$sealed.TimedOut) { Write-Host "DIAGNOSTIC ZIP: $zip" }
                else { if ($result -eq 0) { $result = 1 }; Write-Host 'Archive sealing failed; no shareable ZIP is announced.' }
            } catch {
                if ($result -eq 0) { $result = 1 }
                Write-Host 'Archive sealing failed; inspect root/seal-process stderr. Existing evidence retained.'
            }
        } else { Write-Host 'No verified shareable ZIP; evidence retained locally.' }
        $phaseStatus.final_exit = $result
        $phaseStatus | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'phase-status.json')
        Write-Host "Final exit: $result (preflight/observation failures are preserved independently of packaging)."
        Write-Host "Retained root: $Root; evidence: $evidence"
        $env:READONLY_ADMISSION_TOKEN = $oldToken
    }
    return [int]$result
}
