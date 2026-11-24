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
$window = [RossDiagnostics.Native]::FindTws()
if ($window -ne [IntPtr]::Zero) { [RossDiagnostics.Native]::RestoreTws($window) }
$choice = [System.Windows.Forms.MessageBox]::Show(
    "Show $VolumeSymbol and its full native Volume in TWS. You can arrange TWS while this message is open. After OK, drag once around the watchlist headers and that row. Keep TWS visible and stationary during capture. No phone or clock is needed.",
    'Choose TWS comparison region', [System.Windows.Forms.MessageBoxButtons]::OKCancel
)
if ($choice -ne [System.Windows.Forms.DialogResult]::OK) { throw 'DISPLAY_SELECTION_CANCELLED_NO_CAPTURE_STARTED' }
# The region overlay is local selection only; it never sends input to TWS.
if ($window -ne [IntPtr]::Zero) { [RossDiagnostics.Native]::RestoreTws($window) }
Start-Sleep -Milliseconds 500
$selector = New-Object RossDiagnostics.RegionSelector
try {
    if ($selector.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'DISPLAY_SELECTION_CANCELLED' }
    $region = $selector.Selected
} finally { $selector.Dispose() }
# Bind the actual chosen TWS window, including a title that changed during setup.
# Generic Java apps and regions outside the supported TWS window still refuse.
Start-Sleep -Milliseconds 200
$window = [RossDiagnostics.Native]::WindowForRegion($region)
$null = [RossDiagnostics.Native]::SetForegroundWindow($window)
Start-Sleep -Milliseconds 300
$frames = Join-Path $root 'frames'
$recorder = [RossDiagnostics.VolumeDisplayRecorder]::FromScreen($frames, $window, $region)
$output = New-Object 'System.Collections.Generic.List[string]'
$probeFailure = $null
$screenFailure = $null
try {
    if (!$recorder.Start(10000)) { throw 'DISPLAY_RECORDER_NOT_READY_NO_PROBE_STARTED' }
    # Retain partial output too if the existing bounded probe refuses.
    & (Join-Path $PSScriptRoot 'run_quote_transport_diagnostic.ps1') `
        -ExpectedCommit $ExpectedCommit -ExpectedTree $ExpectedTree `
        -DiagnosticProfile live-volume -VolumeSymbol $VolumeSymbol 6>&1 |
        ForEach-Object { $output.Add([string]$_); Write-Host ([string]$_) }
} catch { $probeFailure = $_.Exception.GetType().Name }
finally {
    try { $recorder.Stop(); $screenFailure = $recorder.Failure }
    finally { $count = $recorder.Count; $recorder.Dispose() }
}
$rootLines = @($output | Where-Object { $_ -cmatch '^live-volume diagnostic only\. Fresh root: C:\\tmp\\qtransport-[0-9a-f]{8}$' })
$status = [ordered]@{
    schema='ROSS_TWS_VOLUME_DISPLAY_CAPTURE_V1'; status='COMPARISON_NOT_VERIFIED'
    source=$ExpectedCommit; frame_count=$count; probe_failure_type=$probeFailure
    screen_failure_type=$screenFailure; PAPER_READY=$false
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
    @{ schema='ROSS_TWS_VOLUME_REVIEW_V1'; symbol=$VolumeSymbol; api_received_at_utc=$received.ToString('o'); frames=$selected } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $review 'review-times.json') -Encoding UTF8
    # Paths and raw API numbers remain in the private local linkage, not the review images.
    @{ probe_path=$probePath; frames_path=$frames } | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $root 'private-linkage.json') -Encoding UTF8
    $status.status = 'DISPLAY_CAPTURE_COMPLETE_UNITS_UNVERIFIED'
    Write-Host ('Review these cropped images locally before sharing: ' + $review)
}
$status | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'capture-status.json') -Encoding UTF8
Write-Host ('Private automatic capture: ' + $root)
Write-Host ($status | ConvertTo-Json -Compress)
if ($status.status -cne 'DISPLAY_CAPTURE_COMPLETE_UNITS_UNVERIFIED') { throw 'DISPLAY_CAPTURE_INCOMPLETE_NO_CALIBRATION_GRANTED' }
