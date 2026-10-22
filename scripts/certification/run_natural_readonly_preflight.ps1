# PREFLIGHT ONLY: no observation/package invocation or continuation on PASS.
param([Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit)
$ErrorActionPreference = 'Stop'
try {
    if (Test-Path -LiteralPath (Join-Path $Root 'e')) { throw 'Fresh evidence root required.' }
    $evidence = New-Item -ItemType Directory -Path (Join-Path $Root 'e')
    . (Join-Path $PSScriptRoot 'Invoke-ReadonlyObservation.ps1')
    $operator = Join-Path $PSScriptRoot 'natural_readonly_operator.py'
    $child = Invoke-ObservationChild -Python $Python -ChildArguments @('-E',$operator,'preflight',$Root,$ExpectedCommit) -LogPrefix (Join-Path $evidence.FullName 'preflight-process') -StopPath (Join-Path $evidence.FullName 'preflight.stop') -BudgetSeconds 90 -StopSeconds 30
    $code = 1
    if ($child.Exited -and !$child.TimedOut -and $child.ExitCode -eq 0) { $code = 0 }
    @{ preflight_exit=$child.ExitCode; final_exit=$code; preflight_timed_out=$child.TimedOut;
       observation_attempted=$false; PAPER_READY=$false; scope='PREFLIGHT_ONLY';
       source_order_mutation_validation='NOT_VERIFIED_BY_PREFLIGHT' } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence.FullName 'preflight-only-status.json')
    Write-Host "Preflight only finished. Raw local evidence: $($evidence.FullName). No observation. PAPER_READY=NO."
    exit $code
} catch {
    Write-Error -ErrorAction Continue $_
    exit 1
}
