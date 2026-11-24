# TITLE: Automatic READ_ONLY volume capture — PRE or RTH
# Use PAPER TWS with Read-Only API enabled. No ticker editing is required.
& {
    $ErrorActionPreference = 'Stop'

    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'Run this in Windows PowerShell 5.1 in PyCharm Terminal.'
    }

    $ny = [TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow, [TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time'))
    if ($ny.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday) -or
        $ny.Hour -lt 4 -or $ny.Hour -ge 16) {
        Write-Host 'No capture started. Run during US pre-market or regular hours.'
        Write-Host 'For 24 November, pre-market starts at 09:00 UK time.'
        return
    }

    $listeners = @(Get-NetTCPConnection -ErrorAction Stop |
        Where-Object { $_.LocalPort -eq 7497 -and $_.State -eq 'Listen' })
    if ($listeners.Count -eq 0) {
        throw 'No API listener on 7497. Complete TWS PAPER login and check API Settings. No capture started.'
    }

    $commit = '8ed0d2d60ab4ed289540a6db47040971643b688a'
    $tree = '77285078996c97dd6aa8ac27210e79785955b35f'
    $expected = 'e9fffdc4429a0ae9b60993f857a8bb1fc823f07bcc5e0c9d2c1aee475933763b'
    $probe = Join-Path $env:TEMP ('ross-volume-' + [guid]::NewGuid().ToString('N') + '.ps1')
    $url = "https://raw.githubusercontent.com/NelzonMamani/ibkr-trading-system/$commit/scripts/certification/run_quote_transport_diagnostic.ps1"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $probe

    if ((Get-FileHash -LiteralPath $probe -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) {
        throw 'READ_ONLY probe hash mismatch. Nothing executed.'
    }
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $probe, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count -ne 0) { throw 'READ_ONLY probe syntax check failed.' }

    Write-Host 'READ_ONLY capture: automatically selecting one current scanner stock.'
    & ($ast.GetScriptBlock()) -DiagnosticProfile live-volume -ExpectedCommit $commit -ExpectedTree $tree
}
# END
