# TITLE: Read connection evidence without reconnecting to IBKR
& {
    $ErrorActionPreference = 'Stop'
    $evidence = 'C:\tmp\qtransport-846349db\e'
    $transport = Get-Content -LiteralPath (Join-Path $evidence 'transport-diagnostic.json') -Raw | ConvertFrom-Json

    $portStatus = 'QUERY_UNAVAILABLE'
    $listenerPresent = $null
    $ipv4Listener = $null
    $establishedRows = $null
    $ownerCategories = @()
    try {
        $rows = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object { $_.LocalPort -eq 7497 })
        $listeners = @($rows | Where-Object { $_.State -eq 'Listen' })
        $listenerPresent = $listeners.Count -gt 0
        $ipv4Listener = @($listeners | Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0') }).Count -gt 0
        $establishedRows = @($rows | Where-Object { $_.State -eq 'Established' }).Count
        $ownerCategories = @(
            foreach ($listener in $listeners) {
                try {
                    $name = (Get-Process -Id $listener.OwningProcess -ErrorAction Stop).ProcessName
                    if ($name -match '^(java|javaw)$') { 'JAVA_PROCESS' }
                    elseif ($name -match '^(tws|ibgateway)$') { 'TWS_OR_GATEWAY_PROCESS' }
                    else { 'OTHER_PROCESS' }
                } catch { 'OWNER_UNAVAILABLE' }
            }
        )
        $portStatus = 'COMPLETE'
    } catch {}

    [pscustomobject]@{
        current_port_7497 = [pscustomobject]@{
            query_status = $portStatus
            listener_present = $listenerPresent
            ipv4_listener_row_present = $ipv4Listener
            established_server_rows = $establishedRows
            listener_owner_categories = @($ownerCategories | Select-Object -Unique)
        }
        transport = $transport | Select-Object coverage_verified,reader_stopped,hooks_restored,hooks_installed_completely
        counters = $transport.counters | Select-Object send_calls,send_requested,send_returned,short_sends,send_exceptions,recv_calls,recv_bytes,recv_eof,recv_timeouts,recv_exceptions,recvmsg_calls,recvmsg_bytes,frames,queue_put,queue_get,decoder_entry,decoder_return,decoder_exception,sdk_logs_suppressed
        events = @($transport.records | Select-Object event,seconds,exception_class,server_version,error_code)
    } | ConvertTo-Json -Depth 6
}
# END
