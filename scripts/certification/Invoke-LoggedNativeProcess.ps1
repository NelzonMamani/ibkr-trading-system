# Process-owned status, independent of PowerShell's scoped $LASTEXITCODE.
function Invoke-LoggedNativeProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $true)][string]$LogPath
    )
    $ErrorActionPreference = 'Stop'
    $writer = $null
    $process = $null
    $childExit = $null
    try {
        # Open before launching: an unusable log must not start verification.
        $encoding = New-Object System.Text.UTF8Encoding($false)
        $writer = New-Object System.IO.StreamWriter($LogPath, $false, $encoding)
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $FilePath
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        # Windows CommandLineToArgvW quoting, including embedded quotes and
        # backslashes immediately before quotes/the closing delimiter.
        $quoted = foreach ($argument in $ArgumentList) {
            '"' + [regex]::Replace([regex]::Replace($argument, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
        }
        $info.Arguments = $quoted -join ' '
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $info
        if (!$process.Start()) { throw 'Child process did not start.' }
        # Drain both streams concurrently; neither full pipe can deadlock exit.
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $childExit = $process.ExitCode
        $outText = $stdout.GetAwaiter().GetResult()
        $errText = $stderr.GetAwaiter().GetResult()
        $writer.Write($outText)
        $writer.Write($errText)
        $writer.Flush()
        $writer.Dispose()
        $writer = $null
        if ($outText) { Write-Host $outText -NoNewline }
        if ($errText) { Write-Host $errText -NoNewline }
        [pscustomobject]@{ ExitCode = $childExit; LogPath = $LogPath }
    } catch {
        # A logging error remains failure even if the child completed with0.
        # Preserve the known child status for the diagnostic; never invent one.
        $_.Exception.Data['ChildExitCode'] = $childExit
        throw
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        if ($null -ne $process) { $process.Dispose() }
    }
}
