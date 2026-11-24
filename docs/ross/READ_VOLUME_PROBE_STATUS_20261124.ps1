# TITLE: Read sanitized status from the failed volume probe
& {
    $ErrorActionPreference = 'Stop'
    $root = 'C:\tmp\qtransport-846349db'
    $evidence = Join-Path $root 'e'
    $readErrors = New-Object 'System.Collections.Generic.List[string]'

    function Read-StatusJson([string]$Name) {
        $path = Join-Path $evidence $Name
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
        try { return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json) }
        catch { $readErrors.Add($Name); return $null }
    }

    function Safe-Fields($Object, [string[]]$Names) {
        $safe = [ordered]@{}
        if ($null -ne $Object) {
            foreach ($name in $Names) {
                $property = $Object.PSObject.Properties[$name]
                if ($null -eq $property) { continue }
                $value = $property.Value
                if ($null -eq $value -or $value -is [bool] -or
                    $value -is [int] -or $value -is [long]) {
                    $safe[$name] = $value
                } elseif ($value -is [double] -and
                          ![double]::IsNaN($value) -and ![double]::IsInfinity($value)) {
                    $safe[$name] = $value
                } elseif ($value -is [string] -and
                          $value -cmatch '^[A-Za-z][A-Za-z0-9_]{0,99}\z') {
                    $safe[$name] = $value
                } else {
                    $safe[$name] = 'NON_TOKEN_VALUE_OMITTED'
                }
            }
        }
        return [pscustomobject]$safe
    }

    $result = Read-StatusJson 'result.json'
    $outer = Read-StatusJson 'outer-status.json'
    $stages = Read-StatusJson 'startup-stages.json'
    $scanner = Read-StatusJson 'scanner.json'
    $acquisition = Read-StatusJson 'acquisition.json'
    $cleanup = Read-StatusJson 'quote-cleanup.json'
    $transport = Read-StatusJson 'transport-diagnostic.json'
    $privacy = Read-StatusJson 'privacy-probe.json'
    $mutations = Read-StatusJson 'mutation-attempts.json'

    [pscustomobject]@{
        result = Safe-Fields $result @(
            'status','exit_code','scope','error_type','cleanup_error_type',
            'disconnect_error_type','validation_error_type','native_volume_sample_status',
            'scanner_attempted','broker_audit_completed','disconnected',
            'source_state','operator_state','final_inventory_complete_empty',
            'transport_evidence_incomplete')
        outer = Safe-Fields $outer @('probe_exit','probe_timed_out','final_exit','scope')
        stages = @(
            foreach ($stage in @($stages)) {
                if ($null -ne $stage) { Safe-Fields $stage @('stage','elapsed_seconds') }
            }
        )
        scanner = Safe-Fields $scanner @(
            'completion_status','end_received','wait_signalled','connected',
            'row_count','error_present','error_code')
        acquisition = Safe-Fields $acquisition @('scan_outcome','native_volume_sample_status')
        quotes = @(
            foreach ($quote in @($acquisition.quotes)) {
                if ($null -ne $quote) {
                    [pscustomobject]@{
                        status = Safe-Fields $quote @(
                            'requested_type','returned_type','snapshot_complete',
                            'diagnostic_fields_available','completion_reason','age_seconds')
                        field_presence = Safe-Fields $quote.field_presence @('bid','ask','last','close','volume')
                    }
                }
            }
        )
        cleanup = Safe-Fields $cleanup @(
            '_active_market_req_ids','_market_events','_market_data',
            '_ticker_by_req_id','_req_id_by_contract_key')
        transport = Safe-Fields $transport @(
            'coverage_verified','absence_claims_valid','cleanup_failed','snapshot_failed')
        privacy = Safe-Fields $privacy @('passed','occurrences')
        mutations = Safe-Fields $mutations @('place','modify','cancel')
        volume_probe_file_exists = [bool](Test-Path -LiteralPath (Join-Path $root 'volume-probe.json') -PathType Leaf)
        unreadable_status_files = @($readErrors.ToArray())
    } | ConvertTo-Json -Depth 8
}
# END
