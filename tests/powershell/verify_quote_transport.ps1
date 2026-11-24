# Parse the actual operator entry with Windows PowerShell5.1; never invoke it.
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot '..\..\scripts\certification\run_quote_transport_diagnostic.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $entry).Path, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Quote diagnostic entry has syntax errors.' }
if ($ast.ParamBlock.Parameters.Count -ne 4) { throw 'Expected commit, explicit profile, tree and volume contract parameters.' }
# Bind only the actual parameter block and pre-body guard, never invoke entry.
$guard = ($ast.EndBlock.Statements[0..1] | ForEach-Object { $_.Extent.Text }) -join "`n"
$binding = [ScriptBlock]::Create($ast.ParamBlock.Extent.Text + "`n" + $guard +
    "`n[pscustomobject]@{ Selected=`$DiagnosticProfile; Tree=`$ExpectedTree; VolumeSymbol=`$VolumeSymbol }")
$pin = 'a' * 40
$tree = 'b' * 40
$defaults = & $binding -ExpectedCommit $pin
if ($defaults.Selected -cne 'quotes') { throw 'Default quote profile changed.' }
$order = & $binding -ExpectedCommit $pin -DiagnosticProfile 'final-orders' -ExpectedTree $tree
if ($order.Selected -cne 'final-orders' -or $order.Tree -cne $tree) { throw 'Explicit profile/tree binding failed.' }
$volume = & $binding -ExpectedCommit $pin -DiagnosticProfile 'live-volume' -ExpectedTree $tree -VolumeSymbol 'SYNTH'
if ($volume.Selected -cne 'live-volume' -or $volume.Tree -cne $tree -or $volume.VolumeSymbol -cne 'SYNTH') {
    throw 'Volume profile/tree/contract binding failed.'
}
$automaticVolume = & $binding -ExpectedCommit $pin -DiagnosticProfile 'live-volume' -ExpectedTree $tree
if ($automaticVolume.Selected -cne 'live-volume' -or $automaticVolume.Tree -cne $tree -or
    ![string]::IsNullOrEmpty($automaticVolume.VolumeSymbol)) {
    throw 'Automatic volume scanner selection binding failed.'
}
foreach ($profile in @('quotes', 'final-orders')) {
    $rejected = $false
    try {
        & $binding -ExpectedCommit $pin -DiagnosticProfile $profile -ExpectedTree $tree -VolumeSymbol 'SYNTH'
    } catch { $rejected = $true }
    if (!$rejected) { throw "Volume contract accepted outside the volume profile: $profile." }
}
foreach ($profile in @('final-orders', 'live-volume')) {
    $rejected = $false
    try {
        if ($profile -ceq 'live-volume') {
            & $binding -ExpectedCommit $pin -DiagnosticProfile $profile -VolumeSymbol 'SYNTH'
        } else {
            & $binding -ExpectedCommit $pin -DiagnosticProfile $profile
        }
    } catch { $rejected = $true }
    if (!$rejected) { throw "Missing reviewed tree accepted for $profile." }
}
$rejected = $false
try { & $binding -ExpectedCommit $pin -DiagnosticProfile 'invalid' -ExpectedTree $tree } catch { $rejected = $true }
if (!$rejected) { throw 'Unknown profile accepted.' }
# Reproduce the old empty-if output hazard, then evaluate ONLY the actual
# argument expressions (not Invoke-ObservationChild, Git or the entry body).
$legacyEmpty = if ($false) { @('unused') } else { @() }
$legacyArgs = @('-E','-u','payload','probe','root','pin') + $legacyEmpty
Write-Host ('LEGACY_EMPTY_BRANCH_ARGUMENT_COUNT=' + $legacyArgs.Count + '; informational only, no assumed null append.')
$assignments = @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -ceq '$profileArgs'
}, $true))
$selection = @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.IfStatementAst] -and
    $n.Extent.Text.Contains('$profileArgs = @($DiagnosticProfile,$ExpectedTree)')
}, $true))
$volumeSelection = @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.IfStatementAst] -and
    $n.Extent.Text.Contains('$profileArgs += @($VolumeSymbol)')
}, $true))
if ($assignments.Count -ne 3 -or $selection.Count -ne 1 -or $volumeSelection.Count -ne 1) {
    throw 'Explicit profile or volume contract argument array missing.'
}
$commands = @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -ceq 'Invoke-ObservationChild'
}, $true))
if ($commands.Count -ne 3) { throw 'Expected exactly probe/package/seal children.' }
foreach ($command in $commands) {
    $elements = $command.CommandElements
    $expression = $null
    for ($i=0; $i -lt $elements.Count-1; $i++) {
        if ($elements[$i] -is [Management.Automation.Language.CommandParameterAst] -and
            $elements[$i].ParameterName -ceq 'ChildArguments') { $expression = $elements[$i+1].Extent.Text }
    }
    if (!$expression) { throw 'Missing child arguments.' }
    $onlyArguments = [ScriptBlock]::Create($ast.ParamBlock.Extent.Text + "`n" + $guard + "`n" +
        '$pin=$ExpectedCommit; $payload="payload"; $root="root";' + "`n" +
        $assignments[0].Extent.Text + "`n" + $selection[0].Extent.Text + "`n" + $volumeSelection[0].Extent.Text + "`n" +
        '$values=' + $expression + '; [pscustomobject]@{Values=$values; Count=$values.Count}')
    $quoteArgs = & $onlyArguments -ExpectedCommit $pin
    $orderArgs = & $onlyArguments -ExpectedCommit $pin -DiagnosticProfile 'final-orders' -ExpectedTree $tree
    $volumeArgs = & $onlyArguments -ExpectedCommit $pin -DiagnosticProfile 'live-volume' -ExpectedTree $tree -VolumeSymbol 'SYNTH'
    $automaticVolumeArgs = & $onlyArguments -ExpectedCommit $pin -DiagnosticProfile 'live-volume' -ExpectedTree $tree
    if ($quoteArgs.Count -ne 6 -or $orderArgs.Count -ne 8 -or $volumeArgs.Count -ne 9 -or
        $automaticVolumeArgs.Count -ne 8) { throw 'Child argument count/scope changed.' }
    if (@($quoteArgs.Values | Where-Object { [string]::IsNullOrEmpty($_) }).Count -ne 0) { throw 'Empty quote argument.' }
    if (@($automaticVolumeArgs.Values | Where-Object { [string]::IsNullOrEmpty($_) }).Count -ne 0) {
        throw 'Automatic volume selection appended an empty contract argument.'
    }
    if ($orderArgs.Values[-2] -cne 'final-orders' -or $orderArgs.Values[-1] -cne $tree) { throw 'Order scope/tree absent.' }
    if ($volumeArgs.Values[-3] -cne 'live-volume' -or $volumeArgs.Values[-2] -cne $tree -or
        $volumeArgs.Values[-1] -cne 'SYNTH') { throw 'Volume scope/tree/contract absent.' }
    if ($automaticVolumeArgs.Values[-2] -cne 'live-volume' -or
        $automaticVolumeArgs.Values[-1] -cne $tree) { throw 'Automatic volume scope/tree absent.' }
}
$privateOnly = @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.IfStatementAst] -and
    $n.Extent.Text.StartsWith("if (`$DiagnosticProfile -eq 'live-volume')") -and
    $n.Extent.Text.Contains('volume-probe.json')
}, $true))
if ($privateOnly.Count -ne 1 -or $privateOnly[0].Extent.EndOffset -ge $commands[1].Extent.StartOffset -or
    !$privateOnly[0].Extent.Text.Contains('return')) {
    throw 'Private volume must return before package or seal.'
}
# Execute only the terminal volume branch against a mocked private JSON reader.
# The native child, filesystem acquisition, package and seal are never invoked.
$onlyVolumeTerminal = [ScriptBlock]::Create(@'
param([int]$exitCode, [string]$ProbeJson)
$DiagnosticProfile = 'live-volume'
$root = 'private-root'
$messages = New-Object 'System.Collections.Generic.List[string]'
$reads = New-Object 'System.Collections.Generic.List[string]'
function Get-Content {
    param([string]$LiteralPath, [switch]$Raw)
    if (!$Raw) { throw 'Private symbol reader must use raw JSON.' }
    $reads.Add($LiteralPath)
    return $ProbeJson
}
function Write-Host {
    param([object]$Object)
    $messages.Add([string]$Object)
}
$failure = $null
try { & {
'@ + "`n" + $privateOnly[0].Extent.Text + "`n" + @'
} } catch { $failure = [string]$_ }
[pscustomobject]@{ Messages=$messages.ToArray(); Reads=$reads.ToArray(); Failure=$failure }
'@)
$privateJson = '{"watchlist":{"symbol":"SYNTH","con_id":9012345,"raw_value":123456},"account":"DU_PRIVATE_SENTINEL"}'
$terminal = & $onlyVolumeTerminal -exitCode 0 -ProbeJson $privateJson
if ($terminal.Failure -or $terminal.Reads.Count -ne 1 -or
    $terminal.Reads[0] -cne (Join-Path 'private-root' 'volume-probe.json') -or
    $terminal.Messages.Count -ne 3 -or $terminal.Messages[-1] -cne 'SYNTH') {
    throw 'Successful private volume branch did not emit only the selected ticker cue.'
}
foreach ($secret in @('9012345', '123456', 'DU_PRIVATE_SENTINEL', '{', '}')) {
    if (($terminal.Messages -join "`n").Contains($secret)) { throw 'Private volume fields reached console.' }
}
$failedProbe = & $onlyVolumeTerminal -exitCode 2 -ProbeJson $privateJson
if (!$failedProbe.Failure -or $failedProbe.Reads.Count -ne 0 -or $failedProbe.Messages.Count -ne 2) {
    throw 'Failed probe read or printed the private symbol cue.'
}
foreach ($invalidJson in @('{"watchlist":{"symbol":"synth"}}',
    '{"watchlist":{"symbol":"SYNTH\n"}}', '{"watchlist":{}}', 'not-json')) {
    $invalidTerminal = & $onlyVolumeTerminal -exitCode 0 -ProbeJson $invalidJson
    if (!$invalidTerminal.Failure -or $invalidTerminal.Messages.Count -ne 2) {
        throw 'Invalid private symbol was printed.'
    }
}
$text = [IO.File]::ReadAllText((Resolve-Path $entry).Path)
foreach ($required in @('-BudgetSeconds 120 -StopSeconds 30', '-BudgetSeconds 90 -StopSeconds 30',
    'Published head differs from reviewed pin.', '$global:LASTEXITCODE',
    'quote_transport_diagnostic.py', 'This profile requires the reviewed tree.',
    'Reviewed tree differs.', 'final-orders-diagnostic-upload.zip', "PAPER_READINESS_GATE='FAIL'")) {
    if (!$text.Contains($required)) { throw "Operator protection missing: $required" }
}
Write-Host 'QUOTE_TRANSPORT_OPERATOR_PARSE=PASS; no child or broker launched.'
