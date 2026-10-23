# Parse the actual operator entry with Windows PowerShell5.1; never invoke it.
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot '..\..\scripts\certification\run_quote_transport_diagnostic.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $entry).Path, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Quote diagnostic entry has syntax errors.' }
if ($ast.ParamBlock.Parameters.Count -ne 1) { throw 'Expected exact commit parameter.' }
$text = [IO.File]::ReadAllText((Resolve-Path $entry).Path)
foreach ($required in @('-BudgetSeconds 120 -StopSeconds 30', '-BudgetSeconds 90 -StopSeconds 30',
    'Published head differs from reviewed pin.', '$global:LASTEXITCODE',
    'quote_transport_diagnostic.py', "PAPER_READINESS_GATE='FAIL'")) {
    if (!$text.Contains($required)) { throw "Operator protection missing: $required" }
}
Write-Host 'QUOTE_TRANSPORT_OPERATOR_PARSE=PASS; no child or broker launched.'
