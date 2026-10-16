# PREPARATION ONLY: clone accepted source and print a separate execution command.
param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
      [Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Use Windows PowerShell 5.1.' }
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Missing Python: $Python" }
$version = (& $Python -E -c 'import sys; print(chr(46).join(map(str,sys.version_info[:3])))' | Out-String).Trim()
if ($global:LASTEXITCODE -ne 0 -or $version -ne '3.13.3') { throw 'Requires the verified Python 3.13.3 environment with repository dependencies.' }
$root = 'C:\tmp\ro-' + [guid]::NewGuid().ToString('N').Substring(0,8)
New-Item -ItemType Directory -Path $root | Out-Null
$checkout = Join-Path $root 's'
& git -c core.longpaths=true clone --no-checkout -- https://github.com/NelzonMamani/ibkr-trading-system.git $checkout
if ($global:LASTEXITCODE -ne 0) { throw 'Clone failed.' }
& git -C $checkout config --local core.longpaths true
if ($global:LASTEXITCODE -ne 0) { throw 'Long-path configuration failed.' }
& git -C $checkout merge-base --is-ancestor $ExpectedCommit origin/main
if ($global:LASTEXITCODE -ne 0) { throw 'Pinned accepted commit is not in fetched main.' }
& git -C $checkout checkout --detach $ExpectedCommit
if ($global:LASTEXITCODE -ne 0) { throw 'Pinned checkout failed.' }
$actual = (& git -C $checkout rev-parse HEAD | Out-String).Trim()
if ($global:LASTEXITCODE -ne 0 -or $actual -cne $ExpectedCommit) { throw 'Checkout identity mismatch.' }
$runner = Join-Path $checkout 'scripts\certification\run_natural_readonly_observation.ps1'
# Preparation does not evaluate session state or start/import runtime/providers.
Write-Host "Prepared $checkout at $actual. Nothing observed. PAPER_READY=NO."
Write-Host 'After the documented TWS/session setup, separately run:'
Write-Host ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Python "{1}" -Root "{2}" -ExpectedCommit {3}' -f $runner,$Python,$root,$ExpectedCommit)
