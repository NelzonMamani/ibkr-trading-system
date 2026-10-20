# User-operated execution only. Preparation never invokes this script.
param([Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
      [ValidateRange(180,1800)][int]$RuntimeSeconds = 180)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'Invoke-ReadonlyObservation.ps1')
    $operator = Join-Path $PSScriptRoot 'natural_readonly_operator.py'
    $status = Invoke-ReadonlyObservation -Python $Python -Operator $operator -Root $Root -ExpectedCommit $ExpectedCommit -RuntimeSeconds $RuntimeSeconds -ObservationSeconds ($RuntimeSeconds + 360)
    if ($status -eq 0) { Write-Host 'Terminal checks passed; review all five outcomes separately. PAPER_READY=NO.' }
    exit $status
} catch {
    Write-Error -ErrorAction Continue $_
    exit 1
}
