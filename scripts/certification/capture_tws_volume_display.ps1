[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedTree,
    [ValidatePattern('^[A-Z][A-Z0-9. -]{0,14}$')][string]$VolumeSymbol = 'LGHL'
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or
    $PSVersionTable.PSVersion.Minor -ne 1) { throw 'WINDOWS_POWERSHELL_51_REQUIRED' }
$source = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$actual = (& git -C $source rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $actual -cne $ExpectedCommit) { throw 'REVIEWED_SOURCE_REQUIRED' }
$actualTree = (& git -C $source rev-parse 'HEAD^{tree}' | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $actualTree -cne $ExpectedTree) { throw 'REVIEWED_TREE_REQUIRED' }
$dirty = @(& git -C $source status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { throw 'CLEAN_SOURCE_REQUIRED' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if ('RossDiagnostics.VolumeDisplayRecorder' -as [type]) { throw 'FRESH_POWERSHELL_PROCESS_REQUIRED' }
Add-Type -Path (Join-Path $PSScriptRoot 'TwsVolumeDisplayCapture.cs') -ReferencedAssemblies @(
    'System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll'
)
[RossDiagnostics.Native]::DpiAware()
$root = Join-Path 'C:\tmp' ('tws-volume-' + [guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $root
Write-Host ('Private automatic capture: ' + $root)
[RossDiagnostics.Native]::DiscoveryJson() | Set-Content -LiteralPath (Join-Path $root 'window-discovery.json') -Encoding UTF8
function Get-VolumeListenerOwners {
    try {
        @(Get-NetTCPConnection -State Listen -LocalPort 7497 -ErrorAction Stop |
            Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::1','::') } |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch { throw 'PAPER_API_LISTENER_QUERY_UNAVAILABLE_NO_NEW_REQUEST' }
}
# Passive OS binding only. No socket is opened to choose the displayed instance.
$owners = @(Get-VolumeListenerOwners)
$discovery = Get-Content -LiteralPath (Join-Path $root 'window-discovery.json') -Raw | ConvertFrom-Json
$discovery | Add-Member -NotePropertyName listener_processes -NotePropertyValue $owners.Count
$discovery | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'window-discovery.json') -Encoding UTF8
if ($owners.Count -ne 1 -or $owners[0] -le 0) { throw 'UNIQUE_PAPER_API_LISTENER_REQUIRED_NO_CAPTURE_STARTED' }
$listenerOwner = [uint32]$owners[0]
$window = [RossDiagnostics.Native]::FindTwsForProcess($listenerOwner)
if ($window -eq [IntPtr]::Zero) { throw 'LISTENER_BOUND_TWS_WINDOW_REQUIRED_NO_CAPTURE_STARTED' }
[RossDiagnostics.Native]::RestoreTws($window)
Start-Sleep -Milliseconds 300
$frames = Join-Path $root 'frames'
$recorder = [RossDiagnostics.VolumeDisplayRecorder]::FromWindow($frames, $window)
Write-Host 'Capturing the TWS client area automatically. Keep it visible and stationary; no selection or recording is needed.'
Write-Host 'Images stay local and may contain account information. Review them before sharing.'
$output = New-Object 'System.Collections.Generic.List[string]'
$probeFailure = $null
$screenFailure = $null
try {
    if (!$recorder.Start(10000)) { throw 'DISPLAY_RECORDER_NOT_READY_NO_PROBE_STARTED' }
    $currentOwners = @(Get-VolumeListenerOwners)
    if ($currentOwners.Count -ne 1 -or [uint32]$currentOwners[0] -ne $listenerOwner) { throw 'PAPER_API_LISTENER_CHANGED_NO_PROBE_STARTED' }
    # Retain partial output too if the existing bounded probe refuses.
    & (Join-Path $PSScriptRoot 'run_quote_transport_diagnostic.ps1') `
        -ExpectedCommit $ExpectedCommit -ExpectedTree $ExpectedTree `
        -DiagnosticProfile live-volume -VolumeSymbol $VolumeSymbol 6>&1 |
        ForEach-Object { $output.Add([string]$_); Write-Host ([string]$_) }
    $currentOwners = @(Get-VolumeListenerOwners)
    if ($currentOwners.Count -ne 1 -or [uint32]$currentOwners[0] -ne $listenerOwner) { throw 'PAPER_API_LISTENER_CHANGED_DURING_CAPTURE' }
} catch { $probeFailure = $_.Exception.GetType().Name }
finally {
    try { $recorder.Stop(); $screenFailure = $recorder.Failure }
    finally { $count = $recorder.Count; $recorder.Dispose() }
}
$rootLines = @($output | Where-Object { $_ -cmatch '^live-volume diagnostic only\. Fresh root: C:\\tmp\\qtransport-[0-9a-f]{8}$' })
$status = [ordered]@{
    schema='ROSS_TWS_VOLUME_DISPLAY_CAPTURE_V1'; status='COMPARISON_NOT_VERIFIED'
    source=$ExpectedCommit; frame_count=$count; probe_failure_type=$probeFailure
    screen_failure_type=$screenFailure; capture_scope='TWS_CLIENT_AREA_NO_REDACTION'; PAPER_READY=$false
}
if ($rootLines.Count -eq 1 -and !$probeFailure -and !$screenFailure) {
    $probeRoot = $rootLines[0].Substring('live-volume diagnostic only. Fresh root: '.Length)
    $receipt = Get-Content -LiteralPath (Join-Path $probeRoot 'e\result.json') -Raw | ConvertFrom-Json
    $outer = Get-Content -LiteralPath (Join-Path $probeRoot 'e\outer-status.json') -Raw | ConvertFrom-Json
    $mutations = Get-Content -LiteralPath (Join-Path $probeRoot 'e\mutation-attempts.json') -Raw | ConvertFrom-Json
    if ($receipt.status -cne 'DIAGNOSTIC_COMPLETE' -or $receipt.exit_code -ne 0 -or $outer.final_exit -ne 0 -or
        $outer.probe_timed_out -ne $false -or $receipt.accepted -cne $ExpectedCommit -or
        $receipt.scope -cne 'LIVE_VOLUME_DIAGNOSTIC_ONLY' -or $receipt.broker_audit_completed -ne $true -or
        $receipt.disconnected -ne $true -or $receipt.source_state -cne 'PASS' -or $receipt.operator_state -cne 'PASS' -or
        $null -eq $mutations.place -or $null -eq $mutations.modify -or $null -eq $mutations.cancel -or
        $mutations.place -ne 0 -or $mutations.modify -ne 0 -or $mutations.cancel -ne 0) {
        throw 'READ_ONLY_COMPLETION_NOT_VERIFIED_KEEP_PRIVATE_EVIDENCE'
    }
    $probePath = Join-Path $probeRoot 'volume-probe.json'
    $probe = Get-Content -LiteralPath $probePath -Raw | ConvertFrom-Json
    if ($probe.watchlist.symbol -cne $VolumeSymbol) { throw 'CAPTURE_CONTRACT_MISMATCH' }
    $received = [datetimeoffset]::Parse($probe.watchlist.received_at_utc)
    $rows = @(Get-Content -LiteralPath (Join-Path $frames 'frames.jsonl') | ForEach-Object {
        $row = $_ | ConvertFrom-Json
        $began = [datetimeoffset]::Parse($row.started_utc)
        $ended = [datetimeoffset]::Parse($row.finished_utc)
        if ($began -gt $ended -or ($ended - $began).TotalMilliseconds -gt 1000 -or
            $began -lt $received.AddSeconds(-15) -or $ended -gt $received.AddSeconds(15)) { return }
        [pscustomobject]@{ row=$row; distance=[Math]::Abs(($began - $received).TotalMilliseconds) }
    } | Sort-Object distance | Select-Object -First 5)
    if (!$rows.Count) { throw 'NO_SCREEN_FRAME_NEAR_API_SAMPLE' }
    $review = Join-Path $root 'review'
    $null = New-Item -ItemType Directory -Path $review
    $selected = @(); $index = 0
    foreach ($item in $rows) {
        $index++
        $name = 'comparison-{0:D2}.png' -f $index
        Copy-Item -LiteralPath (Join-Path $frames $item.row.file) -Destination (Join-Path $review $name)
        $selected += [ordered]@{ file=$name; started_utc=$item.row.started_utc; finished_utc=$item.row.finished_utc }
    }
    @{ schema='ROSS_TWS_VOLUME_REVIEW_V1'; symbol=$VolumeSymbol; capture_scope='TWS_CLIENT_AREA_NO_REDACTION'; api_received_at_utc=$received.ToString('o'); frames=$selected } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $review 'review-times.json') -Encoding UTF8
    # Paths and raw API numbers remain in the private local linkage, not the review images.
    @{ probe_path=$probePath; frames_path=$frames } | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $root 'private-linkage.json') -Encoding UTF8
    $status.status = 'DISPLAY_CAPTURE_COMPLETE_UNITS_UNVERIFIED'
    Write-Host ('Review these private TWS client images locally before sharing: ' + $review)
}
$status | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'capture-status.json') -Encoding UTF8
Write-Host ('Private automatic capture: ' + $root)
Write-Host ($status | ConvertTo-Json -Compress)
if ($status.status -cne 'DISPLAY_CAPTURE_COMPLETE_UNITS_UNVERIFIED') { throw 'DISPLAY_CAPTURE_INCOMPLETE_NO_CALIBRATION_GRANTED' }
