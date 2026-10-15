[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$ExpectedCommit,
    [string]$Python = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $repo
$previousPythonPath = $env:PYTHONPATH
try {
    if (-not (Test-Path $Python -PathType Leaf)) { throw "Python interpreter missing: $Python" }
    $head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -ne $ExpectedCommit) { throw 'Unexpected checkout revision' }
    $dirty = & git status --porcelain=v1 --untracked-files=all --ignore-submodules=none
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Verification requires a clean checkout' }
    $env:PYTHONPATH = (Join-Path $repo 'tests\offline') + ';' + $repo
    & $Python -c "import sys; assert 'sitecustomize' in sys.modules; assert hasattr(sys.modules['sitecustomize'], 'offline')"
    if ($LASTEXITCODE -ne 0) { throw 'Offline guard failed to load' }
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Offline regression suite failed' }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
