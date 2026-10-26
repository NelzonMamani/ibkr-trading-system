# Run only after separate operator authorization. No invocation during preparation.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedTree,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$SourceCheckout,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
    throw 'Windows PowerShell 5.1 is required.'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python executable missing.' }
$source = (Resolve-Path -LiteralPath $SourceCheckout).Path
$head = (& git -C $source rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $ExpectedCommit) { throw 'Exact source head mismatch.' }
$tree = (& git -C $source rev-parse 'HEAD^{tree}' | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $tree -ne $ExpectedTree) { throw 'Exact source tree mismatch.' }
$dirty = (& git -C $source status --porcelain | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Use a clean isolated source checkout.' }
$evidence = [IO.Path]::GetFullPath($EvidenceRoot)
$sourcePrefix = $source.TrimEnd('\') + '\'
if ($evidence.Equals($source,[StringComparison]::OrdinalIgnoreCase) -or
    $evidence.StartsWith($sourcePrefix,[StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $evidence)) { throw 'EvidenceRoot must be new and outside source.' }
$version = (& $Python -I -c 'import sys; assert sys.version_info[:2] == (3,13); print(sys.version.split()[0])' | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Use the reviewed Python 3.13 environment with installed project dependencies.' }
New-Item -ItemType Directory -Path $evidence | Out-Null
# Restrict the new evidence root before any raw body can be written. The child
# output inherits this ACL. Share only the explicit ZIP, never this directory.
$principal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $evidence /inheritance:r /grant:r ('{0}:(OI)(CI)F' -f $principal) | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Private evidence ACL setup failed; acquisition not started.' }
$output = Join-Path $evidence 'batch'
$script = Join-Path $source 'scripts\diagnostics\ross_primary_feed_diagnostic.py'
Write-Host ('DIAGNOSTIC_ONLY; source={0}; tree={1}; Python={2}' -f $head,$tree,$version)
& $Python -I -B $script --acquire --expected-commit $ExpectedCommit --output $output
$diagnosticExit = $LASTEXITCODE
$zip = Join-Path $output 'ross-primary-feed-shareable.zip'
if ($diagnosticExit -eq 1) { $zip = Join-Path $output 'failure\ross-primary-feed-shareable.zip' }
if (Test-Path -LiteralPath $zip -PathType Leaf) {
    Write-Host ('SHARE_ONLY={0}' -f $zip)
    Write-Host ('SHA256={0}' -f (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant())
} else { throw 'No verified shareable ZIP was produced. Keep evidence private.' }
Write-Host ('DIAGNOSTIC_EXIT={0}; PAPER_READY=NO; PAPER_READINESS_GATE=FAIL' -f $diagnosticExit)
# 0 = complete diagnostic coverage, 2 = partial diagnostic coverage, 1 = failure.
# Neither 0 nor a synthetic qualifying classification is Ross natural acceptance.
exit $diagnosticExit
