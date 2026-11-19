# SOURCE PREPARATION ONLY: exact Git objects; no broker/provider/observer launch.
# Separate benchmark capture distribution; frozen Ross release remains unchanged.
& {
    Set-StrictMode -Version 2.0
    $ErrorActionPreference = 'Stop'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'Use Windows PowerShell 5.1 Desktop.'
    }

    $rossFetchRepo = 'C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system'
    $rossFetchPin = 'f53aa41d07ac6143503582d8d2980bd72fe1d90b'
    $rossFetchTree = '8fa63a25c17a3a4567cb1c6cc2f88129c44d796a'
    $rossFetchUrl = 'https://github.com/NelzonMamani/ibkr-trading-system.git'

    function Assert-RossFetchLocalPath {
        param([string]$Path)
        if ($Path -notmatch '^[A-Za-z]:\\') { throw 'Fetch requires existing local absolute Windows paths.' }
        $full = [IO.Path]::GetFullPath($Path)
        $root = [IO.Path]::GetPathRoot($full)
        $drive = New-Object System.IO.DriveInfo -ArgumentList $root
        if ($drive.DriveType -ne [IO.DriveType]::Fixed) { throw 'Fetch paths must be on a local fixed drive.' }
        $cursor = $root
        $parts = @('') + @($full.Substring($root.Length).Split('\') | Where-Object { $_.Length -gt 0 })
        foreach ($part in $parts) {
            if ($part.Length -gt 0) { $cursor = Join-Path $cursor $part }
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if ($item.PSProvider.Name -ne 'FileSystem' -or
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Fetch path ancestry is not an ordinary local filesystem path.'
            }
        }
    }

    if (@(Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_*' }).Count -ne 0) {
        throw 'Inherited GIT_* overrides are not admitted; no fetch or configuration change.'
    }
    $rossFetchGitCommands = @(Get-Command git.exe -CommandType Application -All -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($rossFetchGitCommands.Count -ne 1) { throw 'Native git.exe was not found.' }
    $rossFetchGit = $rossFetchGitCommands[0].Source
    Assert-RossFetchLocalPath $rossFetchGit
    Assert-RossFetchLocalPath $rossFetchRepo

    # Names only: never print credential values or configured headers.
    # Standard LFS and extensions.worktreeconfig are intentionally not rejected.
    $rossFetchUnsafePattern = '^(include\.path|includeif\..*\.path|url\..*\.(insteadof|pushinsteadof)|core\.(hookspath|fsmonitor|sshcommand|gitproxy)|extensions\.partialclone|remote\..*\.(promisor|partialclonefilter|uploadpack|vcs|proxy)|http(\..*)?\.(extraheader|proxy|cookiefile|savecookies|sslverify|sslcert|sslkey|curloptresolve)|https\.proxy)$'
    $rossFetchUnsafeNames = @(& $rossFetchGit --no-optional-locks -C $rossFetchRepo config --no-includes --name-only --get-regexp $rossFetchUnsafePattern)
    $rossFetchConfigExit = $LASTEXITCODE
    if ($rossFetchConfigExit -notin @(0,1)) { throw 'Cannot inspect Git execution and transport configuration.' }
    if ($rossFetchUnsafeNames.Count -ne 0) { throw 'Unadmitted Git execution or transport configuration; no configuration is changed.' }

    $rossFetchTop = @(& $rossFetchGit --no-optional-locks -C $rossFetchRepo rev-parse --show-toplevel)
    if ($LASTEXITCODE -ne 0 -or $rossFetchTop.Count -ne 1 -or
        [IO.Path]::GetFullPath($rossFetchTop[0].Replace('/','\')).TrimEnd('\') -ine $rossFetchRepo.TrimEnd('\')) {
        throw 'The confirmed source path is not the repository root.'
    }
    $rossFetchCommon = @(& $rossFetchGit --no-optional-locks -C $rossFetchRepo rev-parse --git-common-dir)
    if ($LASTEXITCODE -ne 0 -or $rossFetchCommon.Count -ne 1) { throw 'Cannot inspect the repository common directory.' }
    $rossFetchCommonPath = $rossFetchCommon[0].Replace('/','\')
    if (![IO.Path]::IsPathRooted($rossFetchCommonPath)) { $rossFetchCommonPath = Join-Path $rossFetchRepo $rossFetchCommonPath }
    Assert-RossFetchLocalPath $rossFetchCommonPath
    $rossFetchHooks = Join-Path $rossFetchCommonPath 'hooks'
    if (Test-Path -LiteralPath $rossFetchHooks) {
        Assert-RossFetchLocalPath $rossFetchHooks
        $rossFetchActiveHooks = @(Get-ChildItem -LiteralPath $rossFetchHooks -Force -ErrorAction Stop | Where-Object { $_.PSIsContainer -or $_.Name -notlike '*.sample' })
        if ($rossFetchActiveHooks.Count -ne 0) { throw 'Active or unknown Git hooks are present; nothing is disabled or removed.' }
    }

    # --quiet avoids an expected missing-commit error on PowerShell 5.1.
    $rossFetchHavePin = @(& $rossFetchGit --no-optional-locks -C $rossFetchRepo rev-parse --verify --quiet ($rossFetchPin + '^{commit}'))
    $rossFetchPinExit = $LASTEXITCODE
    if ($rossFetchPinExit -notin @(0,1)) { throw 'Cannot inspect the accepted commit locally.' }
    if ($rossFetchPinExit -eq 1) {
        Write-Host 'Downloading the exact accepted benchmark-capture source release; existing branches and working files stay intact.'
        try {
            # Only this native child inherits the temporary noninteractive setting.
            $env:GIT_TERMINAL_PROMPT = '0'
            & $rossFetchGit --no-optional-locks -C $rossFetchRepo `
                -c credential.helper= -c credential.interactive=false -c core.askPass= `
                -c protocol.allow=never -c protocol.https.allow=always `
                -c http.followRedirects=false `
                -c gc.auto=0 -c maintenance.auto=false `
                fetch --no-tags --no-recurse-submodules --no-write-fetch-head `
                --no-auto-maintenance --no-write-commit-graph --no-prune --refmap= `
                $rossFetchUrl $rossFetchPin
            $rossFetchExit = $LASTEXITCODE
        }
        finally {
            Remove-Item Env:GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue
        }
        if ($rossFetchExit -ne 0) { throw 'Exact release download failed; no capture or observer is launched.' }
    }

    $rossFetchVerifiedPin = @(& $rossFetchGit --no-optional-locks -C $rossFetchRepo rev-parse --verify --quiet ($rossFetchPin + '^{commit}'))
    if ($LASTEXITCODE -ne 0 -or $rossFetchVerifiedPin.Count -ne 1 -or $rossFetchVerifiedPin[0] -cne $rossFetchPin) {
        throw 'Accepted commit verification failed; no capture or observer is launched.'
    }
    $rossFetchVerifiedTree = @(& $rossFetchGit --no-optional-locks -C $rossFetchRepo rev-parse --verify --quiet ($rossFetchPin + '^{tree}'))
    if ($LASTEXITCODE -ne 0 -or $rossFetchVerifiedTree.Count -ne 1 -or $rossFetchVerifiedTree[0] -cne $rossFetchTree) {
        throw 'Accepted tree verification failed; no capture or observer is launched.'
    }
    Write-Host 'Accepted benchmark-capture commit and tree verified. No working files or existing run roots changed.'
}
