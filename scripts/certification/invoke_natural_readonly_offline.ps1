[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
    [string]$Python = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe',
    [Parameter(Mandatory = $true)][string]$LogPath
)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'Invoke-LoggedNativeProcess.ps1')
    $shellPath = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop).Source
    $result = Invoke-LoggedNativeProcess -FilePath $shellPath -ArgumentList @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $PSScriptRoot 'verify_natural_readonly_offline.ps1'),
        '-ExpectedCommit', $ExpectedCommit, '-Python', $Python
    ) -LogPath $LogPath
    Write-Host "Verification process exit: $($result.ExitCode)`nLog: $LogPath"
    exit $result.ExitCode
} catch {
    Write-Error ("Verification wrapper failed; child exit: {0}; {1}" -f $_.Exception.Data['ChildExitCode'], $_.Exception.Message) -ErrorAction Continue
    exit 1
}
