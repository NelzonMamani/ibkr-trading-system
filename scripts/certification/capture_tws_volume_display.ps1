[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedTree,
    [ValidatePattern('^[A-Z][A-Z0-9. -]{0,14}$')][string]$VolumeSymbol = 'LGHL',
    [string]$PythonExecutable
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
function Get-VolumeProbeFailureCode {
    param([string]$FailureMessage, [object]$Receipt, [object]$Outer, [string]$Commit)
    # An exception message is input to an exact allowlist only; it is never
    # retained or printed. Completed child receipts are the authority for exits.
    switch -CaseSensitive ($FailureMessage) {
        'DISPLAY_RECORDER_NOT_READY_NO_PROBE_STARTED' { return 'DISPLAY_RECORDER_NOT_READY_NO_PROBE_STARTED' }
        'PAPER_API_LISTENER_QUERY_UNAVAILABLE_NO_NEW_REQUEST' { return 'PAPER_API_LISTENER_QUERY_UNAVAILABLE_NO_NEW_REQUEST' }
        'PAPER_API_LISTENER_CHANGED_NO_PROBE_STARTED' { return 'PAPER_API_LISTENER_CHANGED_NO_PROBE_STARTED' }
        'PAPER_API_LISTENER_CHANGED_DURING_CAPTURE' { return 'PAPER_API_LISTENER_CHANGED_DURING_CAPTURE' }
    }
    if ($Receipt.accepted -ceq $Commit -and $Receipt.scope -ceq 'LIVE_VOLUME_DIAGNOSTIC_ONLY' -and
        $Outer.scope -ceq 'LIVE_VOLUME_DIAGNOSTIC_ONLY') {
        if ($Outer.probe_timed_out -eq $true) { return 'PROBE_TIMED_OUT' }
        if ($Outer.final_exit -eq 2 -and $Receipt.exit_code -eq 2) { return 'PROBE_DIAGNOSTIC_INCOMPLETE' }
        if ($Outer.final_exit -is [int] -and $Outer.final_exit -ne 0) { return 'PROBE_DIAGNOSTIC_FAILED' }
    }
    return 'PROBE_COMMAND_FAILED'
}
function Get-VolumeQuoteDiagnostics {
    param([object]$Acquisition)
    $quotes = @($Acquisition.quotes)
    if (!$quotes.Count -or $null -eq $quotes[0]) { return }
    $quote = $quotes[0]
    $safe = [ordered]@{
        extraction_read_state='READ'; requested_type=$null; returned_type=$null; completion_reason=$null
        snapshot_complete=$null; diagnostic_fields_available=$null; age_seconds=$null
        field_presence=[ordered]@{}; broker_error_count=$null; broker_error_codes=@()
        broker_error_codes_truncated=$null; broker_error_codes_unavailable=$null
    }
    foreach ($name in @('requested_type','returned_type')) {
        if ($quote.$name -cin @('LIVE','FROZEN','DELAYED','DELAYED_FROZEN','UNKNOWN')) { $safe[$name] = $quote.$name }
        elseif ($null -ne $quote.$name) { $safe.extraction_read_state = 'INVALID' }
    }
    if ($quote.completion_reason -cin @('snapshot_end','broker_error','timeout','interrupted')) {
        $safe.completion_reason = $quote.completion_reason
    } elseif ($null -ne $quote.completion_reason) { $safe.extraction_read_state = 'INVALID' }
    foreach ($name in @('snapshot_complete','diagnostic_fields_available',
        'broker_error_codes_truncated','broker_error_codes_unavailable')) {
        if ($quote.$name -is [bool]) { $safe[$name] = $quote.$name }
        elseif ($null -ne $quote.$name) { $safe.extraction_read_state = 'INVALID' }
    }
    $age = $quote.age_seconds
    if (($age -is [int] -or $age -is [long] -or $age -is [double] -or $age -is [decimal]) -and
        ![double]::IsNaN([double]$age) -and ![double]::IsInfinity([double]$age) -and
        $age -ge -315360000 -and $age -le 315360000) { $safe.age_seconds = $age }
    elseif ($null -ne $age) { $safe.extraction_read_state = 'INVALID' }
    foreach ($name in @('bid','ask','last','close','volume')) {
        $value = $quote.field_presence.$name
        $safe.field_presence[$name] = $null
        if ($value -is [bool]) { $safe.field_presence[$name] = $value }
        elseif ($null -ne $value) { $safe.extraction_read_state = 'INVALID' }
    }
    $errorCount = $quote.broker_error_count
    if (($errorCount -is [int] -or $errorCount -is [long]) -and $errorCount -ge 0 -and $errorCount -le 2147483647) {
        $safe.broker_error_count = $errorCount
    } elseif ($null -ne $errorCount) { $safe.extraction_read_state = 'INVALID' }
    $codes = @()
    foreach ($code in @($quote.broker_error_codes)) {
        if ($null -eq $code) { continue }
        if (($code -is [int] -or $code -is [long]) -and $code -ge -2147483648 -and $code -le 2147483647) {
            if ($codes.Count -lt 32) { $codes += [int]$code }
            else { $safe.broker_error_codes_truncated = $true }
        } else { $safe.extraction_read_state = 'INVALID' }
    }
    $safe.broker_error_codes = @($codes | Select-Object -Unique)
    [pscustomobject]$safe
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
$probeFailureMessage = $null
$screenFailure = $null
$screenFailureCode = $null
$screenFailureAt = $null
$runtimeArguments = @{}
if ($PythonExecutable) { $runtimeArguments.PythonExecutable = $PythonExecutable }
try {
    if (!$recorder.Start(10000)) { throw 'DISPLAY_RECORDER_NOT_READY_NO_PROBE_STARTED' }
    $currentOwners = @(Get-VolumeListenerOwners)
    if ($currentOwners.Count -ne 1 -or [uint32]$currentOwners[0] -ne $listenerOwner) { throw 'PAPER_API_LISTENER_CHANGED_NO_PROBE_STARTED' }
    # Retain partial output too if the existing bounded probe refuses.
    & (Join-Path $PSScriptRoot 'run_quote_transport_diagnostic.ps1') `
        -ExpectedCommit $ExpectedCommit -ExpectedTree $ExpectedTree `
        -DiagnosticProfile live-volume -VolumeSymbol $VolumeSymbol @runtimeArguments 6>&1 |
        ForEach-Object { $output.Add([string]$_); Write-Host ([string]$_) }
    $currentOwners = @(Get-VolumeListenerOwners)
    if ($currentOwners.Count -ne 1 -or [uint32]$currentOwners[0] -ne $listenerOwner) { throw 'PAPER_API_LISTENER_CHANGED_DURING_CAPTURE' }
} catch {
    $probeFailure = $_.Exception.GetType().Name
    $probeFailureMessage = $_.Exception.Message
}
finally {
    try {
        $recorder.Stop()
        $screenFailure = $recorder.Failure
        $screenFailureCode = $recorder.FailureCode
        $screenFailureAt = $recorder.UTCFailureAt
    }
    finally { $count = $recorder.Count; $recorder.Dispose() }
}
$rootLines = @($output | Where-Object { $_ -cmatch '^live-volume diagnostic only\. Fresh root: C:\\tmp\\qtransport-[0-9a-f]{8}$' })
$probeReceipt = $null
$probeOuter = $null
$quoteDiagnostics = @()
$quoteReadState = 'MISSING'
$nativeVolumeStatus = $null
$probeResultStatus = $null
if ($rootLines.Count -eq 1) {
    $candidateRoot = $rootLines[0].Substring('live-volume diagnostic only. Fresh root: '.Length)
    # The root is emitted by our unchanged producer and must also carry its
    # matching commit/scope receipt. Failed runs keep local linkage as evidence,
    # without creating a review package or granting calibration.
    try { $probeReceipt = Get-Content -LiteralPath (Join-Path $candidateRoot 'e\result.json') -Raw | ConvertFrom-Json }
    catch { $probeReceipt = $null }
    if ($probeReceipt.accepted -ceq $ExpectedCommit -and $probeReceipt.scope -ceq 'LIVE_VOLUME_DIAGNOSTIC_ONLY') {
        if ($probeReceipt.status -cin @('FAIL','DIAGNOSTIC_ONLY','DIAGNOSTIC_COMPLETE')) {
            $probeResultStatus = $probeReceipt.status
        }
        if ($probeReceipt.native_volume_sample_status -cin @(
            'LIVE_TICK8_CAPTURED_UNITS_UNVERIFIED', 'ROSS_VOLUME_EVIDENCE_MISSING',
            'ROSS_VOLUME_SOURCE_UNSUPPORTED', 'ROSS_VOLUME_DATA_NOT_LIVE',
            'ROSS_VOLUME_SCOPE_MISMATCH', 'ROSS_VOLUME_STALE_OR_UNTIMED',
            'ROSS_VOLUME_VALUE_INVALID', 'PAPER_RELEASE_VOLUME_NATIVE_PROBE_INCOMPLETE',
            'PAPER_RELEASE_VOLUME_HISTORICAL_PROBE_UNVERIFIED')) {
            $nativeVolumeStatus = $probeReceipt.native_volume_sample_status
        }
        try { $probeOuter = Get-Content -LiteralPath (Join-Path $candidateRoot 'e\outer-status.json') -Raw | ConvertFrom-Json }
        catch { $probeOuter = $null }
        $privateProbePath = Join-Path $candidateRoot 'volume-probe.json'
        if (!(Test-Path -LiteralPath $privateProbePath -PathType Leaf)) { $privateProbePath = $null }
        @{ schema='ROSS_TWS_VOLUME_PRIVATE_LINKAGE_V1'; source=$ExpectedCommit;
           probe_root=$candidateRoot; probe_path=$privateProbePath; frames_path=$frames } | ConvertTo-Json |
            Set-Content -LiteralPath (Join-Path $root 'private-linkage.json') -Encoding UTF8
        $acquisitionPath = Join-Path $candidateRoot 'e\acquisition.json'
        if (Test-Path -LiteralPath $acquisitionPath -PathType Leaf) {
            try {
                $acquisition = Get-Content -LiteralPath $acquisitionPath -Raw | ConvertFrom-Json
                $quoteDiagnostics = @(Get-VolumeQuoteDiagnostics -Acquisition $acquisition)
                $quoteReadState = if ($quoteDiagnostics.Count) { $quoteDiagnostics[0].extraction_read_state } else { 'READ' }
            } catch { $quoteReadState = 'INVALID'; $quoteDiagnostics = @() }
        }
    }
}
$probeFailureCode = if ($probeFailure) {
    Get-VolumeProbeFailureCode -FailureMessage $probeFailureMessage -Receipt $probeReceipt -Outer $probeOuter -Commit $ExpectedCommit
} else { $null }
$probeFailureMessage = $null
$status = [ordered]@{
    schema='ROSS_TWS_VOLUME_DISPLAY_CAPTURE_V1'; status='COMPARISON_NOT_VERIFIED'
    source=$ExpectedCommit; frame_count=$count; probe_failure_type=$probeFailure
    probe_failure_code=$probeFailureCode; screen_failure_type=$screenFailure
    screen_failure_code=$screenFailureCode; screen_failure_at_utc=$screenFailureAt
    quote_diagnostics_read_state=$quoteReadState; quote_diagnostics=$quoteDiagnostics
    probe_result_status=$probeResultStatus; native_volume_sample_status=$nativeVolumeStatus
    capture_scope='TWS_CLIENT_AREA_NO_REDACTION'; PAPER_READY=$false
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
    $status.status = 'DISPLAY_CAPTURE_COMPLETE_UNITS_UNVERIFIED'
    Write-Host ('Review these private TWS client images locally before sharing: ' + $review)
}
$status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $root 'capture-status.json') -Encoding UTF8
Write-Host ('Private automatic capture: ' + $root)
Write-Host ($status | ConvertTo-Json -Depth 6 -Compress)
if ($status.status -cne 'DISPLAY_CAPTURE_COMPLETE_UNITS_UNVERIFIED') { throw 'DISPLAY_CAPTURE_INCOMPLETE_NO_CALIBRATION_GRANTED' }
