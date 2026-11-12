# PREPARED ONLY: no observation, preflight or connection was run to create this file.
# Run the whole block on the authorized Windows laptop in Windows PowerShell 5.1
# Desktop (-NoProfile is recommended), under its CURRENT execution policy.
# If policy blocks a maintained script, STOP; do not change permissions/policy.
# Release editing only: repin Commit AND Tree together after the eventual First
# merge and its required CI/main verification. Do not substitute an arbitrary HEAD.
& {
    Set-StrictMode -Version 2.0
    $ErrorActionPreference = 'Stop'
    $release = [pscustomobject]@{
        Commit = '14c8d01c5bfd7e3f70678210422cbcb65aac46d6'
        Tree = '8eb1b88aa9fda2540cfc4a78f159b4b4df7acc8c'
        PreparationBlob = '5cbb8bcdbed3041b41f5fce7cd64b1bf72a37ee4'
        # Exact accepted ASCII preparation file, allowing only LF or CRLF checkout bytes.
        PreparationFileSha256 = @('25166f54a9ad17c0b8fc6877d9cfd100f9b00d1a05e9ade669b08606d48d6c2c',
                                  'd5f6d869f186180e90d268412f7be8195227a2e18050fa83bc219622dfef424b')
        RuntimeSeconds = 900
    }
    $resolvedRunRoot = $null

    function Assert-NoReparseAncestry {
        param([string]$Path)
        $node = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        while ($null -ne $node) {
            if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'A selected path or ancestor is a junction/symlink/reparse point; physical local/outside-root placement is unverified.'
            }
            $parentPath = Split-Path -Path $node.FullName -Parent
            if ([string]::IsNullOrEmpty($parentPath) -or $parentPath -eq $node.FullName) { break }
            $node = Get-Item -LiteralPath $parentPath -Force -ErrorAction Stop
        }
    }

    function Read-ExistingFilesystemPath {
        param([string]$Prompt, [ValidateSet('Leaf','Container')][string]$Kind)
        $entered = Read-Host $Prompt
        if ([string]::IsNullOrWhiteSpace($entered)) { throw 'Missing path; nothing launched.' }
        $entered = $entered.Trim()
        if ($entered.Length -ge 2 -and $entered.StartsWith('"') -and $entered.EndsWith('"')) {
            $entered = $entered.Substring(1, $entered.Length - 2)
        }
        if ($entered -notmatch '^[A-Za-z]:[\\/]' -or $entered.StartsWith('\\')) {
            throw 'Use an explicit local absolute Windows path; no guessed or remote path.'
        }
        if (!(Test-Path -LiteralPath $entered -PathType $Kind)) { throw 'Selected path/type does not exist.' }
        $resolved = Resolve-Path -LiteralPath $entered -ErrorAction Stop
        if ($resolved.Provider.Name -ne 'FileSystem') { throw 'A filesystem path is required.' }
        $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($resolved.ProviderPath))
        if ($drive.DriveType -eq [IO.DriveType]::Network -or $drive.DriveType -eq [IO.DriveType]::Unknown) {
            throw 'Selected path must resolve on a known local drive, not a network mapping.'
        }
        Assert-NoReparseAncestry -Path $resolved.ProviderPath
        return $resolved.ProviderPath
    }

    function Invoke-CheckedGit {
        param([string]$GitExe, [string]$At, [string[]]$Arguments)
        $lines = @(& $GitExe --no-optional-locks -C $At @Arguments)
        $gitExit = $global:LASTEXITCODE
        if ($gitExit -ne 0) { throw ('Git check failed (exit {0}); no observation launch.' -f $gitExit) }
        return $lines
    }

    try {
        if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSEdition -ne 'Desktop' -or
            $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
            throw 'Refused: use the authorized local Windows laptop and Windows PowerShell 5.1 Desktop.'
        }
        $windowsPowerShell = Join-Path $PSHOME 'powershell.exe'
        if (!(Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) { throw 'Windows PowerShell executable is unavailable.' }
        $gitCommand = Get-Command git.exe -CommandType Application -ErrorAction Stop
        $gitExe = $gitCommand.Source
        $plainGit = Get-Command git -ErrorAction Stop
        if ($plainGit.CommandType -ne 'Application' -or $plainGit.Source -ine $gitExe) {
            throw 'Unqualified git is shadowed or differs from git.exe; maintained preparation cannot be admitted.'
        }
        if (@(Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_*' }).Count -ne 0) {
            throw 'Git environment overrides are present; their behavior is unverified. Nothing is changed automatically.'
        }

        # These three real paths are supplied NOW, not assumed from an old block.
        $sourceCheckout = Read-ExistingFilesystemPath -Prompt 'Actual existing repository checkout ROOT path' -Kind Container
        $pythonExe = Read-ExistingFilesystemPath -Prompt 'Actual dependency-equipped Windows Python 3.13.3 python.exe path' -Kind Leaf
        $evidenceBase = Read-ExistingFilesystemPath -Prompt 'Actual existing LOCAL evidence BASE directory (outside source and all previous run roots)' -Kind Container
        $sourcePrefix = $sourceCheckout.TrimEnd('\') + '\'
        if ($evidenceBase.TrimEnd('\') -ieq $sourceCheckout.TrimEnd('\') -or
            $evidenceBase.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Evidence base must be outside the source checkout; nothing is reset or deleted.'
        }
        # Preserve old runs: do not nest this attempt inside a prior owned root.
        $ancestor = Get-Item -LiteralPath $evidenceBase -ErrorAction Stop
        while ($null -ne $ancestor) {
            foreach ($marker in @('runner.json','admission.json','operator-state-source.json','s\.git')) {
                if (Test-Path -LiteralPath (Join-Path $ancestor.FullName $marker)) {
                    throw 'Evidence base is inside an existing prepared/run root; choose a separate base. Existing data is preserved.'
                }
            }
            $ancestor = $ancestor.Parent
        }

        # Inspect only Git execution surfaces used by this exact preparation.
        # Config reads do not execute hooks, filters or fsmonitor. Refuse unknown
        # include/conditional-include behavior before any worktree/status command.
        $unsafeConfig = @(& $gitExe --no-optional-locks -C $sourceCheckout config --no-includes --get-regexp '^(include\.path|includeif\..*\.path|core\.(hookspath|fsmonitor)|filter\..*\.(smudge|clean|process)|extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$')
        $configExit = $global:LASTEXITCODE
        if ($configExit -notin @(0,1)) { throw 'Cannot inspect Git execution configuration; no preparation.' }
        if ($unsafeConfig.Count -ne 0) { throw 'Configured Git includes/hooks/fsmonitor/filters or partial/promisor clone behavior is not admitted by this block; no configuration is changed.' }
        $repoTop = ((Invoke-CheckedGit -GitExe $gitExe -At $sourceCheckout -Arguments @('rev-parse','--show-toplevel')) -join '').Trim()
        $repoTop = [IO.Path]::GetFullPath($repoTop.Replace('/','\'))
        if ($repoTop.TrimEnd('\') -ine $sourceCheckout.TrimEnd('\')) { throw 'Select the actual repository root, not a subdirectory.' }
        $commonDir = ((Invoke-CheckedGit -GitExe $gitExe -At $sourceCheckout -Arguments @('rev-parse','--git-common-dir')) -join '').Trim()
        if (![IO.Path]::IsPathRooted($commonDir)) { $commonDir = Join-Path $sourceCheckout $commonDir }
        $commonDir = [IO.Path]::GetFullPath($commonDir)
        Assert-NoReparseAncestry -Path $commonDir
        $hooksDir = Join-Path $commonDir 'hooks'
        if (Test-Path -LiteralPath $hooksDir) {
            Assert-NoReparseAncestry -Path $hooksDir
            if (!(Test-Path -LiteralPath $hooksDir -PathType Container)) { throw 'Git hooks path is not an inspectable directory.' }
            $activeHooks = @(Get-ChildItem -LiteralPath $hooksDir -Force -ErrorAction Stop | Where-Object { $_.PSIsContainer -or $_.Name -notlike '*.sample' })
            if ($activeHooks.Count -ne 0) { throw 'Active or unknown Git hooks are present; no preparation or hook/config modification.' }
        }
        # Local objects only: no fetch, clone, transport/credential helper,
        # checkout/reset of the existing source, or arbitrary HEAD substitution.
        $localPin = @(& $gitExe --no-optional-locks -C $sourceCheckout cat-file -e ($release.Commit + '^{commit}'))
        if ($global:LASTEXITCODE -ne 0) { throw 'Reviewed accepted commit is missing locally. Stop: obtain that reviewed release separately; this block never fetches or changes its pin.' }
        $pinTree = ((Invoke-CheckedGit -GitExe $gitExe -At $sourceCheckout -Arguments @('rev-parse',($release.Commit + '^{tree}'))) -join '').Trim()
        if ($pinTree -cne $release.Tree) { throw 'Accepted commit/tree binding differs.' }
        $prepareRelative = 'docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1'
        $prepareObject = $release.Commit + ':' + $prepareRelative
        $prepareBlob = ((Invoke-CheckedGit -GitExe $gitExe -At $sourceCheckout -Arguments @('rev-parse',$prepareObject)) -join '').Trim()
        if ($prepareBlob -cne $release.PreparationBlob) { throw 'Maintained preparation owner changed; review it before repinning.' }
        $prepareFile = Join-Path $sourceCheckout $prepareRelative
        if (!(Test-Path -LiteralPath $prepareFile -PathType Leaf)) { throw 'Maintained pinned preparation FILE is missing from the selected checkout.' }
        Assert-NoReparseAncestry -Path $prepareFile
        $prepareFileHash = (Get-FileHash -LiteralPath $prepareFile -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
        if ($release.PreparationFileSha256 -notcontains $prepareFileHash) { throw 'Preparation file bytes differ from the authenticated accepted owner; no execution.' }

        $beforeRoots = @(Get-ChildItem -LiteralPath $evidenceBase -Directory -Force -Filter 'ro-*' -ErrorAction Stop | ForEach-Object { $_.FullName })
        # Invoke the authenticated maintained FILE normally: current execution
        # policy applies here too. It makes a fresh worktree, not a connection.
        $prepareMessages = @(& $prepareFile -ExpectedCommit $release.Commit -Python $pythonExe -SourceCheckout $sourceCheckout -BaseDirectory $evidenceBase -RuntimeSeconds $release.RuntimeSeconds 6>&1)
        foreach ($message in $prepareMessages) {
            $display = [string]$message
            # The owner prints a separate example. Replace that display only;
            # this block performs its one current-policy launch below instead.
            if ($display.StartsWith('powershell.exe -NoProfile -', [StringComparison]::OrdinalIgnoreCase)) {
                Write-Host 'Preparation example not executed. Continue only through this block below.'
            } else { Write-Host $display }
        }
        $afterRoots = @(Get-ChildItem -LiteralPath $evidenceBase -Directory -Force -Filter 'ro-*' -ErrorAction Stop)
        $freshRoots = @($afterRoots | Where-Object { $beforeRoots -notcontains $_.FullName })
        if ($freshRoots.Count -ne 1 -or $freshRoots[0].Name -cnotmatch '^ro-[0-9a-f]{8}$') {
            throw 'Cannot identify exactly ONE newly owner-created run root; no newest-folder guessing or launch.'
        }
        $resolvedRunRoot = (Resolve-Path -LiteralPath $freshRoots[0].FullName -ErrorAction Stop).ProviderPath
        $preparedCheckout = Join-Path $resolvedRunRoot 's'
        $resolvedEvidence = [IO.Path]::GetFullPath((Join-Path $resolvedRunRoot 'e'))
        $runner = Join-Path $preparedCheckout 'scripts\certification\run_natural_readonly_observation.ps1'
        foreach ($unused in @('e','state','runner.json','admission.json')) {
            if (Test-Path -LiteralPath (Join-Path $resolvedRunRoot $unused)) { throw 'Fresh admission state already exists; no root reuse/resume.' }
        }
        if (!(Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Maintained runner missing from prepared checkout.' }
        $preparedHead = ((Invoke-CheckedGit -GitExe $gitExe -At $preparedCheckout -Arguments @('rev-parse','HEAD')) -join '').Trim()
        $preparedTree = ((Invoke-CheckedGit -GitExe $gitExe -At $preparedCheckout -Arguments @('rev-parse','HEAD^{tree}')) -join '').Trim()
        $preparedStatus = @(Invoke-CheckedGit -GitExe $gitExe -At $preparedCheckout -Arguments @('status','--porcelain'))
        if ($preparedHead -cne $release.Commit -or $preparedTree -cne $release.Tree -or $preparedStatus.Count -ne 0) {
            throw 'Prepared pin/tree/cleanliness check failed; no observation launch.'
        }
        Write-Host ('Resolved FRESH run root: ' + $resolvedRunRoot)
        Write-Host ('Resolved FRESH evidence destination: ' + $resolvedEvidence)
        Write-Host ('Pinned commit: ' + $release.Commit)
        Write-Host 'Existing local contract: 127.0.0.1:7497, client71, READ_ONLY, one900-second attempt.'

        Write-Host 'REQUIRED CONTEMPORANEOUS OPERATOR VERIFICATION (NOT machine/API-proven by this block):'
        Write-Host '1. This is the authorized Windows laptop. TWS visibly shows the intended PAPER login; do not infer PAPER from port7497.'
        Write-Host '2. TWS Read-Only API and the socket setting are ALREADY enabled at127.0.0.1:7497; the local listener belongs to that TWS. No settings/permissions are changed here.'
        Write-Host '3. Client71 is verified free and reserved for this single attempt. No other Ross runtime, pytest session or independent broker operation is active or will be started during it.'
        Write-Host '4. Required market/scanner data login and entitlements are already active. Holdings, orders and recovery/submission state will remain untouched.'
        Write-Host 'If ANY fact is unknown, unverifiable, false or conflicting, STOP. Do not probe, change permissions or terminate a client to make it pass.'
        $attestation = Read-Host 'Only after checking every fact, type exactly VERIFIED LOCAL PAPER READONLY CLIENT71 (anything else refuses launch)'
        if ($attestation -cne 'VERIFIED LOCAL PAPER READONLY CLIENT71') { throw 'Required local prerequisites were not verified; observation was not launched.' }
        $attestationPath = Join-Path $resolvedRunRoot 'local-operator-attestations.json'
        [ordered]@{
            scope = 'OPERATOR_ATTESTED_LOCAL_PREREQUISITES_NOT_MACHINE_PROOF'
            attested_utc = [datetime]::UtcNow.ToString('o')
            source_commit = $release.Commit
            runtime_seconds = $release.RuntimeSeconds
            endpoint = '127.0.0.1:7497'
            client_id = 71
            facts = @('LOCAL_WINDOWS_LAPTOP','INTENDED_PAPER_LOGIN','TWS_API_READ_ONLY_ALREADY_ENABLED','LOCAL_LISTENER_BELONGS_TO_TWS','CLIENT71_FREE_AND_RESERVED','NO_CONCURRENT_RUNTIME_PYTEST_OR_BROKER_OPERATION','EXISTING_MARKET_DATA_LOGIN','NO_HOLDINGS_ORDERS_RECOVERY_OR_PERMISSION_CHANGES')
            machine_preflight_status = 'NOT_RUN_YET_EXISTING_OWNER_MUST_PASS'
            PAPER_READY = $false
        } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $attestationPath -Encoding UTF8 -ErrorAction Stop

        Write-Host ('Separate LOCAL operator-attestation file: ' + $attestationPath)
        Write-Host 'Retain that file separately: it is outside root/e and is NOT automatically included in the sealed ZIP.'

        Write-Host 'Now invoking the existing prepare->preflight->observe->package->seal owner ONCE; no separate preflight-only run.'
        Write-Host 'It verifies exact Windows Python3.13.3/source/config/guards, canonical RTH with the full1260s observation envelope remaining, recognized runtime inventory and fresh single-use admission.'
        Write-Host 'Cleanup remains identity-scoped to its newly owned runtime. No wrapper kill, connection probe, external-client termination, retry or recovery clearing is added.'
        # No execution-policy override. A policy refusal must remain a refusal.
        & $windowsPowerShell -NoProfile -File $runner -Python $pythonExe -Root $resolvedRunRoot -ExpectedCommit $release.Commit -RuntimeSeconds $release.RuntimeSeconds
        $ownerExit = [int]$global:LASTEXITCODE
        Write-Host ('Maintained runner exit: ' + $ownerExit + '; retained root: ' + $resolvedRunRoot)
        if ($ownerExit -ne 0) { throw ('Maintained runner returned{0}; preserve evidence, no retry/resume. Its phase-status retains the exact exits.' -f $ownerExit) }
        Write-Host 'Runner exit0 is not paper readiness or all-five-outcome acceptance. Review terminal safety, natural scans, issuer coverage, catalyst qualification and downstream progression separately. PAPER_READY=NO.'
    } catch {
        if ($null -ne $resolvedRunRoot) { Write-Host ('Retained root (do not reuse): ' + $resolvedRunRoot) }
        Write-Host 'Stopped. No automatic retry, cleanup of other clients, permission change or recovery action is authorized by this block.'
        throw
    }
}
