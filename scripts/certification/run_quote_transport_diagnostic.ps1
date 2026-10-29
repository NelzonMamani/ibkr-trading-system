[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
      [ValidateSet('quotes','final-orders')][string]$DiagnosticProfile = 'quotes',
      [ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedTree)
if ($DiagnosticProfile -eq 'final-orders' -and !$ExpectedTree) { throw 'Final orders requires explicit reviewed tree.' }
& {
    $ErrorActionPreference = 'Stop'
    $pin = $ExpectedCommit
    $source = 'C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system'
    $python = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
    $base = 'C:\tmp'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5) {
        throw 'Use Windows PowerShell5.1.'
    }
    if (!(Test-Path $python -PathType Leaf) -or !(Test-Path $base -PathType Container)) {
        throw 'Verified Python/base directory missing.'
    }
    # Interpreter/platform checks run inside the supervised120s child.
    $publishedRef = if ($DiagnosticProfile -eq 'final-orders') { $pin } else { 'codex/quote-transport-diagnostic' }
    & git -C $source fetch origin $publishedRef
    if ($global:LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
    $published = (& git -C $source rev-parse FETCH_HEAD | Out-String).Trim()
    if ($global:LASTEXITCODE -ne 0 -or $published -cne $pin) { throw 'Published head differs from reviewed pin.' }
    $tree = (& git -C $source rev-parse ($pin + '^{tree}') | Out-String).Trim()
    if ($global:LASTEXITCODE -ne 0) { throw 'Reviewed tree unavailable.' }
    if ($DiagnosticProfile -eq 'final-orders' -and $tree -cne $ExpectedTree) { throw 'Reviewed tree differs.' }
    $entries = @(& git -C $source ls-tree -r -l $pin)
    if ($global:LASTEXITCODE -ne 0) { throw 'Cannot estimate checkout size.' }
    [long]$bytes = 0
    foreach ($line in $entries) {
        if ($line -match '^\d+ blob [0-9a-f]+\s+(\d+)\t') { $bytes += [long]$Matches[1] }
    }
    $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($base))
    if ($drive.AvailableFreeSpace -lt [Math]::Max(536870912, $bytes * 1.25 + 268435456)) {
        throw 'Insufficient free space; nothing deleted.'
    }
    $root = Join-Path $base ('qtransport-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $root | Out-Null
    $checkout = Join-Path $root 's'
    & git -C $source -c core.longpaths=true worktree add --detach $checkout $pin
    if ($global:LASTEXITCODE -ne 0) { throw "Preparation failed; retain $root." }
    $actual = (& git -C $checkout rev-parse HEAD | Out-String).Trim()
    if ($global:LASTEXITCODE -ne 0 -or $actual -cne $pin) { throw 'Checkout commit mismatch.' }
    $actualTree = (& git -C $checkout rev-parse 'HEAD^{tree}' | Out-String).Trim()
    if ($global:LASTEXITCODE -ne 0 -or $actualTree -cne $tree) { throw 'Checkout tree mismatch.' }
    $evidence = Join-Path $root 'e'
    New-Item -ItemType Directory -Path $evidence | Out-Null
    $payload = Join-Path $checkout 'scripts\certification\quote_transport_diagnostic.py'
    . (Join-Path $checkout 'scripts\certification\Invoke-ReadonlyObservation.ps1')
    Write-Host "$DiagnosticProfile diagnostic only. Fresh root: $root"
    Write-Host 'Normal RTH and PAPER TWS Read-Only API127.0.0.1:7497; unused client71 required.'
    Write-Host "Cooperative stop: New-Item -ItemType File -Force '$evidence\STOP_REQUESTED'"
    $profileArgs = if ($DiagnosticProfile -eq 'final-orders') { @($DiagnosticProfile,$ExpectedTree) } else { @() }
    $probe = Invoke-ObservationChild -Python $python `
        -ChildArguments (@('-E','-u',$payload,'probe',$root,$pin) + $profileArgs) `
        -LogPrefix (Join-Path $evidence 'probe-process') `
        -StopPath (Join-Path $evidence 'STOP_REQUESTED') -BudgetSeconds 120 -StopSeconds 30
    # A live/unproven child causes Invoke-ObservationChild to throw: no packaging.
    if (!$probe.Exited) { throw 'Probe exit unverified; retain local evidence.' }
    $exitCode = if ($probe.TimedOut) { 124 } else { $probe.ExitCode }
    @{ probe_exit=$probe.ExitCode; probe_timed_out=$probe.TimedOut; final_exit=$exitCode;
       scope=$(if ($DiagnosticProfile -eq 'final-orders') { 'FINAL_ORDERS_DIAGNOSTIC_ONLY' } else { 'QUOTE_DIAGNOSTIC_ONLY' }); PAPER_READY=$false; PAPER_READINESS_GATE='FAIL' } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'outer-status.json')
    $packagePrefix = Join-Path $root 'package-process'
    $package = Invoke-ObservationChild -Python $python `
        -ChildArguments (@('-E','-u',$payload,'package',$root,$pin) + $profileArgs) `
        -LogPrefix $packagePrefix -StopPath (Join-Path $evidence 'PACKAGE_STOP_REQUESTED') `
        -BudgetSeconds 90 -StopSeconds 30
    if (!$package.Exited -or $package.TimedOut -or $package.ExitCode -ne 0) {
        throw "Packaging/ privacy verification failed; retain $root. No ZIP announced."
    }
    foreach ($suffix in @('.stdout.log','.stderr.log','.process.json')) {
        Copy-Item -LiteralPath ($packagePrefix + $suffix) -Destination $evidence
    }
    $sealed = Invoke-ObservationChild -Python $python `
        -ChildArguments (@('-E','-u',$payload,'seal',$root,$pin) + $profileArgs) `
        -LogPrefix (Join-Path $root 'seal-process') `
        -StopPath (Join-Path $evidence 'PACKAGE_STOP_REQUESTED') -BudgetSeconds 90 -StopSeconds 30
    $zipName = if ($DiagnosticProfile -eq 'final-orders') { 'final-orders-diagnostic-upload.zip' } else { 'quote-diagnostic-upload.zip' }
    $zip = Join-Path $root $zipName
    if (!$sealed.Exited -or $sealed.TimedOut -or $sealed.ExitCode -ne 0 -or !(Test-Path $zip -PathType Leaf)) {
        throw "Privacy sealing failed; retain $root. No ZIP announced."
    }
    Write-Host "PRIVACY-VERIFIED DIAGNOSTIC ZIP: $zip"
    Write-Host "Probe effective exit: $exitCode. Inspect result.json and outer-status.json separately."
    Write-Host 'Exit0 means this bounded diagnostic completed; it is not natural Ross acceptance.'
    Write-Host "Retained root: $root; PAPER_READY=NO. Do not retry automatically."
    if ($exitCode -ne 0) { throw "Diagnostic nonzero exit $exitCode; preserve the archive and all local evidence." }
}
