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


    function Assert-UnusedStandardSystemLfs {
        param([string]$At, [ValidateSet('source','working')][string]$Mode)
        # Binary NUL-framed Git plumbing stays inside Python subprocess pipes.
        # Native --source is mandatory: index/worktree substitution is forbidden.
        $qualificationProgram = @'
"""Embedded external-operator qualification; no checkout, filters or broker activity."""
import hashlib, json, ntpath, os, pathlib, re, subprocess, sys

STANDARD = {b'filter.lfs.clean': b'git-lfs clean -- %f',
            b'filter.lfs.smudge': b'git-lfs smudge -- %f',
            b'filter.lfs.process': b'git-lfs filter-process'}
OPTIONAL = {b'filter.lfs.required': b'true'}
_WINDOWS = sys.platform == 'win32'
UNSAFE = re.compile(rb'^(include\.path|includeif\..*\.path|core\.(hookspath|fsmonitor)|extensions\.(partialclone|worktreeconfig)|remote\..*\.(promisor|partialclonefilter)|attr\.tree)$')

def _windows_drive_type(root):
    import ctypes
    api = ctypes.WinDLL('kernel32', use_last_error=True).GetDriveTypeW
    api.argtypes = [ctypes.c_wchar_p]
    api.restype = ctypes.c_uint
    return int(api(root))

def _attribute_source_location(name, repo):
    # No attribute-source filesystem access until lexical location and, on
    # Windows, native root-drive classification establish known local scope.
    if not name or '\0' in name or name.startswith(('\\\\', '//')):
        raise ValueError('UNC/device or unresolved attribute-source location')
    if _WINDOWS:
        value = name.replace('/', '\\')
        drive, tail = ntpath.splitdrive(value)
        if drive:
            if not re.fullmatch('[A-Za-z]:', drive) or not tail.startswith('\\'):
                raise ValueError('Unresolved drive-relative attribute source')
        else:
            if tail.startswith('\\'):
                raise ValueError('Unresolved root-relative attribute source')
            value = ntpath.join(repo, value)
        value = ntpath.normpath(value)
        if not re.match(r'^[A-Za-z]:\\', value):
            raise ValueError('Attribute source lacks a fully qualified local drive')
        # UNKNOWN(0), NO_ROOT_DIR(1), REMOTE(4) and unsupported results refuse.
        if _windows_drive_type(value[:3]) not in (2, 3, 5, 6):
            raise ValueError('Network, unknown or unresolved attribute-source drive')
        return value
    if ntpath.splitdrive(name)[0] or name.startswith('\\'):
        raise ValueError('Attribute-source location cannot be resolved locally')
    return os.path.abspath(os.path.join(repo, name))

def qualify(git, repo, commit, tree, working=False):
    def run(*args, data=None, absent=False):
        p = subprocess.run([git, '--no-optional-locks', '-C', repo, *args], input=data,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if p.stderr or p.returncode not in ((0, 1) if absent else (0,)):
            raise ValueError('Native Git inspection unsupported, failed or emitted diagnostics')
        return p.stdout
    def records(raw, width):
        if not raw or not raw.endswith(b'\0'):
            raise ValueError('Incomplete NUL-framed Git inspection')
        parts = raw[:-1].split(b'\0')
        if len(parts) % width:
            raise ValueError('Ambiguous Git inspection framing')
        return [parts[i:i+width] for i in range(0, len(parts), width)]
    def config():
        raw = run('config', '--no-includes', '--null', '--show-origin', '--show-scope', '--list')
        entries = records(raw, 3)
        seen = set()
        for scope, origin, item in entries:
            if b'\n' not in item: raise ValueError('Incomplete config key/value')
            key, value = item.split(b'\n', 1)
            if UNSAFE.fullmatch(key): raise ValueError('Unadmitted Git execution/source configuration')
            if key.lower().startswith(b'filter.'):
                allowed = STANDARD.get(key, OPTIONAL.get(key))
                if allowed is None or value != allowed or scope != b'system' or not origin.startswith(b'file:') or len(origin) <= 5 or key in seen:
                    raise ValueError('Only exact non-overridden standard system-origin LFS definitions qualify')
                seen.add(key)
            if key == b'core.attributesfile':
                # Relative paths differ across the source and new linked checkout.
                if not os.path.isabs(os.fsdecode(value)):
                    raise ValueError('Relative or tilde attribute-file configuration is ambiguous across worktrees')
        if seen and (seen & set(STANDARD)) != set(STANDARD):
            raise ValueError('Incomplete standard LFS command set')
        return raw, entries, seen
    def externals(entries):
        explicit = any(item.split(b'\n', 1)[0].lower() == b'core.attributesfile' for _, _, item in entries)
        result = []
        for label, args in [('info', ('rev-parse', '--git-path', 'info/attributes')),
                            ('global', ('var', 'GIT_ATTR_GLOBAL')),
                            ('system', ('var', 'GIT_ATTR_SYSTEM'))]:
            raw = run(*args)
            if not raw.endswith(b'\n') or b'\n' in raw.rstrip(b'\r\n'):
                raise ValueError('Attribute source path is incomplete or ambiguous')
            name = os.fsdecode(raw.rstrip(b'\r\n'))
            path = pathlib.Path(_attribute_source_location(name, repo))
            # Verify parents before touching descendants through a junction.
            for ancestor in reversed([path, *path.parents]):
                try: stat = ancestor.lstat()
                except FileNotFoundError: continue
                if ancestor.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('Unverified attribute-source reparse ancestry')
            if path.exists():
                if not path.is_file(): raise ValueError('Attribute source is not a regular file')
                payload = path.read_bytes()
            else:
                if label == 'global' and explicit:
                    raise ValueError('Configured attribute file is missing')
                payload = None
            result.append([label, os.fsencode(str(path)).hex(), None if payload is None else payload.hex()])
        return result
    before, entries, seen = config()
    sources = externals(entries)
    actual = run('rev-parse', '--verify', commit + '^{tree}').strip()
    if actual != tree.encode('ascii'): raise ValueError('Pinned commit/tree differs')
    paths = run('ls-tree', '-r', '-t', '-z', '--full-tree', '--name-only', tree)
    names = [p[0] for p in records(paths, 1)]
    if any(not p or p.startswith(b'/') for p in names) or len(set(names)) != len(names):
        raise ValueError('Incomplete or ambiguous target-tree path inventory')
    def attributes(source):
        args = ['check-attr', '-z', '--stdin']
        if source: args.append('--source=' + tree)
        raw = run(*args, 'filter', data=paths)
        rows = records(raw, 3)
        if len(rows) != len(names): raise ValueError('Incomplete filter-attribute coverage')
        for expected, (name, attr, value) in zip(names, rows):
            if name != expected or attr != b'filter' or value not in (b'unspecified', b'unset'):
                raise ValueError('Active, ambiguous or incomplete effective filter attribute')
        return raw
    pinned = attributes(True)
    live = attributes(False) if working else b''
    after, entries_after, _ = config()
    if after != before or externals(entries_after) != sources:
        raise ValueError('Relevant configuration/attributes changed during inspection')
    digest = hashlib.sha256(before + paths + pinned + live + json.dumps(sources, sort_keys=True).encode()).hexdigest()
    return {'snapshot': digest, 'paths': len(names), 'standard_system_lfs_keys': len(seen),
            'native_pinned_tree': tree, 'working_tree_also_qualified': working}

if __name__ == '__main__':
    try:
        if len(sys.argv) != 6 or sys.argv[5] not in ('source', 'working'):
            raise ValueError('Incomplete qualification arguments')
        print(json.dumps(qualify(*sys.argv[1:5], working=sys.argv[5] == 'working'), sort_keys=True))
    except Exception as error:
        print('FILTER_QUALIFICATION_REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)
'@
        $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($qualificationProgram))
        $bootstrap = "import base64;exec(base64.b64decode('$encoded'))"
        $answer = @(& $pythonExe -E -c $bootstrap $gitExe $At $release.Commit $release.Tree $Mode)
        if ($global:LASTEXITCODE -ne 0 -or $answer.Count -ne 1) {
            throw 'Complete native pinned-tree filter qualification failed; no preparation or launch.'
        }
        $qualified = $answer[0] | ConvertFrom-Json -ErrorAction Stop
        if ($qualified.snapshot -cnotmatch '^[0-9a-f]{64}$' -or $qualified.paths -lt 1 -or
            $qualified.native_pinned_tree -cne $release.Tree -or
            $qualified.working_tree_also_qualified -ne ($Mode -eq 'working')) {
            throw 'Incomplete qualification result; no preparation or launch.'
        }
        return [string]$qualified.snapshot
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
        $unsafeConfig = @(& $gitExe --no-optional-locks -C $sourceCheckout config --no-includes --get-regexp '^(include\.path|includeif\..*\.path|core\.(hookspath|fsmonitor)|extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$')
        $configExit = $global:LASTEXITCODE
        if ($configExit -notin @(0,1)) { throw 'Cannot inspect Git execution configuration; no preparation.' }
        if ($unsafeConfig.Count -ne 0) { throw 'Configured Git includes/hooks/fsmonitor or partial/promisor clone behavior is not admitted by this block; no configuration is changed.' }
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

        # Only the exact complete system-origin LFS triplet, with optional
        # system-origin required=true metadata, may qualify, and only
        # when ALL pinned paths have native effective filter=unspecified/unset.
        $sourceFilterSnapshot = Assert-UnusedStandardSystemLfs -At $sourceCheckout -Mode source
        $beforeRoots = @(Get-ChildItem -LiteralPath $evidenceBase -Directory -Force -Filter 'ro-*' -ErrorAction Stop | ForEach-Object { $_.FullName })
        # Invoke the authenticated maintained FILE normally: current execution
        # policy applies here too. It makes a fresh worktree, not a connection.
        if ((Assert-UnusedStandardSystemLfs -At $sourceCheckout -Mode source) -cne $sourceFilterSnapshot) {
            throw 'Filter/configuration facts changed before checkout; no preparation.'
        }
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
        if ((Assert-UnusedStandardSystemLfs -At $sourceCheckout -Mode source) -cne $sourceFilterSnapshot) {
            throw 'Source filter/configuration facts changed during preparation; no launch.'
        }
        $preparedFilterSnapshot = Assert-UnusedStandardSystemLfs -At $preparedCheckout -Mode working
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
        # Requalify immediately before the maintained owner's attribute-sensitive
        # status/admission boundary. No config edits or filter suppression.
        if ((Assert-UnusedStandardSystemLfs -At $sourceCheckout -Mode source) -cne $sourceFilterSnapshot -or
            (Assert-UnusedStandardSystemLfs -At $preparedCheckout -Mode working) -cne $preparedFilterSnapshot) {
            throw 'Relevant filter/configuration facts changed before runner admission; no launch.'
        }
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
