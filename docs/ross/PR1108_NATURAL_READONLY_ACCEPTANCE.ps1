# PREPARATION ONLY. Reuse local Git objects; never clone or touch old evidence.
param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
      [Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$SourceCheckout,
      [string]$BaseDirectory = 'C:\tmp',
      [ValidateRange(180,1800)][int]$RuntimeSeconds = 180)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Use Windows PowerShell 5.1.' }
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Missing Python: $Python" }
$version = (& $Python -E -c 'import sys; print(chr(46).join(map(str,sys.version_info[:3])))' | Out-String).Trim()
if ($global:LASTEXITCODE -ne 0 -or $version -ne '3.13.3') { throw 'Requires the verified Python 3.13.3 environment with repository dependencies.' }
& git -C $SourceCheckout cat-file -e ($ExpectedCommit + '^{commit}')
if ($global:LASTEXITCODE -ne 0) { throw 'Pinned commit is missing locally; fetch the reviewed repair branch first.' }
if (!(Test-Path -LiteralPath $BaseDirectory -PathType Container)) { throw 'BaseDirectory must already exist.' }
$base = (Resolve-Path -LiteralPath $BaseDirectory).Path
$drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($base))
# Estimate one checked-out tree plus a conservative evidence/state reserve.
$tree = @(& git -C $SourceCheckout ls-tree -r -l $ExpectedCommit)
if ($global:LASTEXITCODE -ne 0) { throw 'Cannot estimate pinned checkout size.' }
[long]$treeBytes = 0
foreach ($line in $tree) { if ($line -match '^\d+ blob [0-9a-f]+\s+(\d+)\t') { $treeBytes += [long]$Matches[1] } }
[long]$needed = [Math]::Max(536870912, [Math]::Ceiling($treeBytes * 1.25) + 268435456)
Write-Host "Free bytes: $($drive.AvailableFreeSpace); required estimate: $needed; Git history will be shared."
if ($drive.AvailableFreeSpace -lt $needed) { throw 'Insufficient free space; choose another BaseDirectory or free space manually. Nothing deleted.' }
$root = Join-Path $base ('ro-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $root | Out-Null
$checkout = Join-Path $root 's'
& git -C $SourceCheckout -c core.longpaths=true worktree add --detach $checkout $ExpectedCommit
if ($global:LASTEXITCODE -ne 0) { throw "Worktree preparation failed; retained $root. Existing evidence untouched." }
$actual = (& git -C $checkout rev-parse HEAD | Out-String).Trim()
if ($global:LASTEXITCODE -ne 0 -or $actual -cne $ExpectedCommit) { throw 'Checkout identity mismatch.' }
# Checkout/interpreter setup above is outside the conservative2000s runner wait allowance.
# Runner: prepare150/30, preflight150/30, observe1260/30 (900 runtime),
# package150/30, seal90/30; two5s pipe drains per phase. Not hard real-time.
$runner = Join-Path $checkout 'scripts\certification\run_natural_readonly_observation.ps1'
Write-Host "Prepared $checkout at $actual. Nothing observed. PAPER_READY=NO."
Write-Host 'After the documented TWS/session setup, separately run:'
Write-Host ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Python "{1}" -Root "{2}" -ExpectedCommit {3} -RuntimeSeconds {4}' -f $runner,$Python,$root,$ExpectedCommit,$RuntimeSeconds)
