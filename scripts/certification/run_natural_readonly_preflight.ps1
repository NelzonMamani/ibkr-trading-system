# Filesystem preparation + final preflight ONLY; never resumes into observation.
param([Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'Invoke-ReadonlyObservation.ps1')
    $operator = Join-Path $PSScriptRoot 'natural_readonly_operator.py'
    $result = Invoke-ReadonlyObservation -Python $Python -Operator $operator -Root $Root -ExpectedCommit $ExpectedCommit -PreflightOnly
    $code = if ($result -eq 0) { 0 } else { 1 }
    @{ preflight_exit=$result; final_exit=$code; observation_attempted=$false; PAPER_READY=$false; scope='PREFLIGHT_ONLY';
       source_order_mutation_validation='NOT_VERIFIED_BY_PREFLIGHT' } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Root 'e/preflight-only-status.json')
    exit $code
} catch { Write-Error -ErrorAction Continue $_; exit 1 }
