# Generic process boundary: tests supply controlled children; released runner fixes the operator.
function Invoke-ObservationChild {
    param([string]$Python, [string[]]$ChildArguments, [string]$LogPrefix,
          [string]$StopPath, [double]$BudgetSeconds, [double]$StopSeconds = 30,
          [scriptblock]$LogStreamFactory = { param($path) [IO.File]::Open($path, 'Create', 'Write', 'Read') })
    $ErrorActionPreference = 'Stop'
    $process = $null; $outFile = $null; $errFile = $null
    $code = $null; $exited = $false; $timedOut = $false; $started = $false; $stopWaited = $false; $childError = $null
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
        if (!$process.Start()) { throw 'Child launch failed.' }
        $started = $true
        $childId = $process.Id
        # Retain the handle before exit; never depend on scoped LASTEXITCODE.
        $null = $process.Handle
        $outCopy = $process.StandardOutput.BaseStream.CopyToAsync($outFile)
        $errCopy = $process.StandardError.BaseStream.CopyToAsync($errFile)
        $clock = [Diagnostics.Stopwatch]::StartNew()
        while (!$process.WaitForExit(200)) {
            if ($outCopy.IsFaulted -or $errCopy.IsFaulted) { throw 'Child log write failed.' }
            if ($clock.Elapsed.TotalSeconds -ge $BudgetSeconds) {
                $timedOut = $true
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
        # Descendants holding a pipe cannot make cleanup wait indefinitely.
        if (!$outCopy.Wait(5000) -or !$errCopy.Wait(5000)) { throw 'Child pipes did not close within budget.' }
        $outFile.Flush(); $errFile.Flush()
        [pscustomobject]@{ ExitCode = $code; TimedOut = $timedOut; Exited = $true; ProcessId = $childId }
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
          [double]$PreflightSeconds = 90, [double]$ObservationSeconds = 540,
          [double]$StopSeconds = 30, [double]$PackageSeconds = 90)
    $ErrorActionPreference = 'Stop'
    $evidence = Join-Path $Root 'e'
    if (Test-Path -LiteralPath $evidence) { throw 'Evidence already exists; prepare a fresh run root. Existing evidence preserved.' }
    [IO.Directory]::CreateDirectory($evidence) | Out-Null
    $stop = Join-Path $evidence 'terminal\STOP_REQUESTED'
    $result = 1; $canPackage = $true
    $phaseStatus = [ordered]@{ preflight_exit=$null; observation_exit=$null; package_exit=$null; final_exit=$null; package_status='NOT_STARTED' }
    try {
        $canPackage = $false
        $preflight = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$Operator,'preflight',$Root,$ExpectedCommit) -LogPrefix (Join-Path $evidence 'preflight-process') -BudgetSeconds $PreflightSeconds -StopSeconds $StopSeconds
        $canPackage = $true
        $result = $preflight.ExitCode
        $phaseStatus.preflight_exit = $result
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
        if ($preflight.TimedOut) { throw 'Preflight timed out; no observation launch.' }
        if ($result -eq 0) {
            Write-Host "Logs: $evidence\terminal\stdout.log and stderr.log"
            Write-Host "Early graceful stop: New-Item -ItemType File -Force '$stop'"
            try {
                $canPackage = $false
                $observed = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$Operator,'observe',$Root,$ExpectedCommit) -LogPrefix (Join-Path $evidence 'supervisor') -StopPath $stop -BudgetSeconds $ObservationSeconds -StopSeconds $StopSeconds
                $canPackage = $true
                $result = $observed.ExitCode
                $phaseStatus.observation_exit = $result
                if ($observed.TimedOut -and $result -eq 0) { $result = 124 }
            } catch {
                # Never package files while a supervisor may still own writers.
                $canPackage = [bool]$_.Exception.Data['ChildExited']
                throw
            }
        }
    } catch {
        if ($result -eq 0) { $result = 1 }
        $phaseStatus.outer_error = $_.Exception.GetType().Name
        if ($_.Exception.Data.Contains('ChildStarted')) {
            $canPackage = !$_.Exception.Data['ChildStarted'] -or [bool]$_.Exception.Data['ChildExited']
        }
        throw
    } finally {
        if ($canPackage) {
            $phaseStatus.package_status = 'RUNNING'
            $phaseStatus | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'phase-status-before-package.json')
            try {
                $packaged = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$Operator,'package',$Root,$ExpectedCommit) -LogPrefix (Join-Path $evidence 'package-process') -BudgetSeconds $PackageSeconds -StopSeconds $StopSeconds
                $phaseStatus.package_exit = $packaged.ExitCode
                $phaseStatus.package_status = if ($packaged.TimedOut) { 'TIMEOUT' } elseif ($packaged.ExitCode -eq 0) { 'PASS' } else { 'NONZERO' }
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
        if ($canPackage -and $phaseStatus.package_exit -in @(0,2) -and (Test-Path -LiteralPath $zip -PathType Leaf)) {
            try {
                $sealed = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$Operator,'seal',$Root,$ExpectedCommit) -LogPrefix (Join-Path $Root 'seal-process') -BudgetSeconds $PackageSeconds -StopSeconds $StopSeconds
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
    }
    return [int]$result
}
