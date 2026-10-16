# Generic process boundary: tests supply controlled children; released runner fixes the operator.
function Invoke-ObservationChild {
    param([string]$Python, [string[]]$ChildArguments, [string]$LogPrefix,
          [string]$StopPath, [double]$BudgetSeconds, [double]$StopSeconds = 30,
          [scriptblock]$LogStreamFactory = { param($path) [IO.File]::Open($path, 'Create', 'Write', 'Read') })
    $ErrorActionPreference = 'Stop'
    $process = $null; $outFile = $null; $errFile = $null
    $code = $null; $exited = $false; $timedOut = $false; $started = $false
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
        if ($started -and !$exited) {
            try {
                if ($StopPath) {
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($StopPath)) | Out-Null
                    [IO.File]::WriteAllText($StopPath, "GRACEFUL_STOP_REQUESTED`n")
                }
                $exited = $process.WaitForExit([int]($StopSeconds * 1000))
                if ($exited) { $code = $process.ExitCode }
            } catch { }
        }
        $childError.Exception.Data['ChildStarted'] = $started
        $childError.Exception.Data['ChildExitCode'] = $code
        $childError.Exception.Data['ChildExited'] = $exited
        throw $childError
    } finally {
        if ($null -ne $outFile) { $outFile.Dispose() }
        if ($null -ne $errFile) { $errFile.Dispose() }
        if ($null -ne $process) { $process.Dispose() }
    }
}
function Invoke-ReadonlyObservation {
    param([string]$Python, [string]$Operator, [string]$Root, [string]$ExpectedCommit,
          [double]$PreflightSeconds = 90, [double]$ObservationSeconds = 540,
          [double]$StopSeconds = 30, [double]$PackageSeconds = 90)
    $ErrorActionPreference = 'Stop'
    $evidence = Join-Path $Root 'e'
    [IO.Directory]::CreateDirectory($evidence) | Out-Null
    $stop = Join-Path $evidence 'terminal\STOP_REQUESTED'
    $result = 1; $canPackage = $true
    try {
        $preflight = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$Operator,'preflight',$Root,$ExpectedCommit) -LogPrefix (Join-Path $evidence 'preflight-process') -BudgetSeconds $PreflightSeconds -StopSeconds $StopSeconds
        $result = $preflight.ExitCode
        if ($preflight.TimedOut) { throw 'Preflight timed out; no observation launch.' }
        if ($result -eq 0) {
            Write-Host "Logs: $evidence\terminal\stdout.log and stderr.log"
            Write-Host "Early graceful stop: New-Item -ItemType File -Force '$stop'"
            try {
                $observed = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$Operator,'observe',$Root,$ExpectedCommit) -LogPrefix (Join-Path $evidence 'supervisor') -StopPath $stop -BudgetSeconds $ObservationSeconds -StopSeconds $StopSeconds
                $result = $observed.ExitCode
                if ($observed.TimedOut -and $result -eq 0) { $result = 124 }
            } catch {
                # Never package files while a supervisor may still own writers.
                $canPackage = [bool]$_.Exception.Data['ChildExited']
                throw
            }
        }
    } catch {
        $canPackage = !$_.Exception.Data['ChildStarted'] -or [bool]$_.Exception.Data['ChildExited']
        throw
    } finally {
        if ($canPackage) {
            $packaged = Invoke-ObservationChild -Python $Python -ChildArguments @('-E','-u',$Operator,'package',$Root,$ExpectedCommit) -LogPrefix (Join-Path $evidence 'package-process') -BudgetSeconds $PackageSeconds -StopSeconds $StopSeconds
            if ($result -eq 0 -and ($packaged.ExitCode -ne 0 -or $packaged.TimedOut)) {
                $result = if ($packaged.ExitCode -ne 0) { $packaged.ExitCode } else { 124 }
            }
        }
        Write-Host "Retained root: $Root; evidence: $evidence"
    }
    return [int]$result
}
