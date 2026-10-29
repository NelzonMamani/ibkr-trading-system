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
$text = [IO.File]::ReadAllText((Resolve-Path $entry).Path)
foreach ($required in @('-BudgetSeconds 120 -StopSeconds 30', '-BudgetSeconds 90 -StopSeconds 30',
    'Published head differs from reviewed pin.', '$global:LASTEXITCODE',
    'quote_transport_diagnostic.py', 'Final orders requires explicit reviewed tree.',
    'Reviewed tree differs.', 'final-orders-diagnostic-upload.zip', "PAPER_READINESS_GATE='FAIL'")) {
    if (!$text.Contains($required)) { throw "Operator protection missing: $required" }
}
Write-Host 'QUOTE_TRANSPORT_OPERATOR_PARSE=PASS; no child or broker launched.'
