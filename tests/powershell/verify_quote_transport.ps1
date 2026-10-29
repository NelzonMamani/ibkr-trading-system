# Parse the actual operator entry with Windows PowerShell5.1; never invoke it.
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot '..\..\scripts\certification\run_quote_transport_diagnostic.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $entry).Path, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Quote diagnostic entry has syntax errors.' }
if ($ast.ParamBlock.Parameters.Count -ne 3) { throw 'Expected commit, explicit profile and tree parameters.' }
# Bind only the actual parameter block and pre-body guard, never invoke entry.
$guard = $ast.EndBlock.Statements[0].Extent.Text
$binding = [ScriptBlock]::Create($ast.ParamBlock.Extent.Text + "`n" + $guard +
    "`n[pscustomobject]@{ Selected=`$DiagnosticProfile; Tree=`$ExpectedTree }")
$pin = 'a' * 40
$tree = 'b' * 40
$defaults = & $binding -ExpectedCommit $pin
if ($defaults.Selected -cne 'quotes') { throw 'Default quote profile changed.' }
$order = & $binding -ExpectedCommit $pin -DiagnosticProfile 'final-orders' -ExpectedTree $tree
if ($order.Selected -cne 'final-orders' -or $order.Tree -cne $tree) { throw 'Explicit profile/tree binding failed.' }
$rejected = $false
try { & $binding -ExpectedCommit $pin -DiagnosticProfile 'final-orders' } catch { $rejected = $true }
if (!$rejected) { throw 'Missing reviewed tree accepted.' }
$rejected = $false
try { & $binding -ExpectedCommit $pin -DiagnosticProfile 'invalid' -ExpectedTree $tree } catch { $rejected = $true }
if (!$rejected) { throw 'Unknown profile accepted.' }
# Reproduce the old empty-if output hazard, then evaluate ONLY the actual
# argument expressions (not Invoke-ObservationChild, Git or the entry body).
$legacyEmpty = if ($false) { @('unused') } else { @() }
$legacyArgs = @('-E','-u','payload','probe','root','pin') + $legacyEmpty
if ($legacyArgs.Count -ne 7 -or $null -ne $legacyArgs[-1]) { throw 'Empty-if null control changed.' }
$assignments = @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -ceq '$profileArgs'
}, $true))
$selection = @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.IfStatementAst] -and
    $n.Extent.Text.StartsWith("if (`$DiagnosticProfile -eq 'final-orders')") -and
    $n.Extent.Text.Contains('$profileArgs')
}, $true))
if ($assignments.Count -ne 2 -or $selection.Count -ne 1) { throw 'Explicit profile argument array missing.' }
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
        $assignments[0].Extent.Text + "`n" + $selection[0].Extent.Text + "`n" +
        '$values=' + $expression + '; [pscustomobject]@{Values=$values; Count=$values.Count}')
    $quoteArgs = & $onlyArguments -ExpectedCommit $pin
    $orderArgs = & $onlyArguments -ExpectedCommit $pin -DiagnosticProfile 'final-orders' -ExpectedTree $tree
    if ($quoteArgs.Count -ne 6 -or $orderArgs.Count -ne 8) { throw 'Child argument count/scope changed.' }
    if (@($quoteArgs.Values | Where-Object { [string]::IsNullOrEmpty($_) }).Count -ne 0) { throw 'Empty quote argument.' }
    if ($orderArgs.Values[-2] -cne 'final-orders' -or $orderArgs.Values[-1] -cne $tree) { throw 'Order scope/tree absent.' }
}
$text = [IO.File]::ReadAllText((Resolve-Path $entry).Path)
foreach ($required in @('-BudgetSeconds 120 -StopSeconds 30', '-BudgetSeconds 90 -StopSeconds 30',
    'Published head differs from reviewed pin.', '$global:LASTEXITCODE',
    'quote_transport_diagnostic.py', 'Final orders requires explicit reviewed tree.',
    'Reviewed tree differs.', 'final-orders-diagnostic-upload.zip', "PAPER_READINESS_GATE='FAIL'")) {
    if (!$text.Contains($required)) { throw "Operator protection missing: $required" }
}
Write-Host 'QUOTE_TRANSPORT_OPERATOR_PARSE=PASS; no child or broker launched.'
