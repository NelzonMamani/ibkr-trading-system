# Native Windows PowerShell 5.1: compile the actual helper and exercise image
# readiness, write failure, timestamping and joined cleanup using synthetic pixels.
# No TWS, broker, desktop screenshot or network is involved in these controls.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$entry = Join-Path $repo 'scripts\certification\capture_tws_volume_display.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($entry, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'AUTOMATIC_DISPLAY_OPERATOR_PARSE_FAILED' }
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Path (Join-Path $repo 'scripts\certification\TwsVolumeDisplayCapture.cs') -ReferencedAssemblies @(
    'System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll'
)
$fixture = @'
using System;
using System.Drawing;
using System.Threading;
using RossDiagnostics;
public static class SyntheticVolumeFrames {
    public static VolumeDisplayRecorder Good(string path) {
        return new VolumeDisplayRecorder(path, delegate {
            Bitmap image = new Bitmap(120, 50);
            using (Graphics g = Graphics.FromImage(image)) g.Clear(Color.Red);
            return image;
        });
    }
    public static VolumeDisplayRecorder Failed(string path) {
        return new VolumeDisplayRecorder(path, delegate { throw new InvalidOperationException("Synthetic private error"); });
    }
    public static VolumeDisplayRecorder Slow(string path) {
        return new VolumeDisplayRecorder(path, delegate { Thread.Sleep(500); return new Bitmap(120, 50); });
    }
}
'@
# Compile fixture and helper together, since Add-Type's in-memory assembly is not
# a disk reference available to a second compiler invocation.
$helper = Get-Content -LiteralPath (Join-Path $repo 'scripts\certification\TwsVolumeDisplayCapture.cs') -Raw
$fixtureSource = $fixture -replace '(?m)^using .*;\r?\n', ''
Add-Type -TypeDefinition (($helper -replace 'namespace RossDiagnostics', 'namespace RossDiagnosticsControls') +
    ($fixtureSource -replace '\bVolumeDisplayRecorder\b', 'RossDiagnosticsControls.VolumeDisplayRecorder')) `
    -ReferencedAssemblies @('System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll')
$root = Join-Path $env:RUNNER_TEMP ('tws-display-controls-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $root
$goodPath = Join-Path $root 'good'
$good = [SyntheticVolumeFrames]::Good($goodPath)
try {
    if (!$good.Start(3000)) { throw 'FIRST_FRAME_NOT_READY' }
    $good.Stop(); $before = $good.Count
    Start-Sleep -Milliseconds 600
    if ($good.Count -ne $before -or $good.Count -lt 1 -or $good.Failure) { throw 'STOP_DID_NOT_JOIN_FRAME_OWNER' }
    $rows = @(Get-Content -LiteralPath (Join-Path $goodPath 'frames.jsonl') | ForEach-Object { $_ | ConvertFrom-Json })
    if ($rows.Count -ne $before) { throw 'FRAME_MANIFEST_COUNT_MISMATCH' }
    foreach ($row in $rows) {
        if ([datetimeoffset]::Parse($row.started_utc) -gt [datetimeoffset]::Parse($row.finished_utc)) { throw 'FRAME_CLOCK_ORDER_FAILED' }
        $image = [Drawing.Bitmap]::FromFile((Join-Path $goodPath $row.file))
        try { if ($image.GetPixel(0,0).ToArgb() -ne [Drawing.Color]::Red.ToArgb()) { throw 'SAVED_PIXELS_DIFFER' } }
        finally { $image.Dispose() }
    }
} finally { $good.Dispose() }
$failedPath = Join-Path $root 'failed'
$failed = [SyntheticVolumeFrames]::Failed($failedPath)
try {
    if ($failed.Start(3000) -or $failed.Count -ne 0 -or $failed.Failure -cne 'InvalidOperationException') { throw 'FIRST_CAPTURE_FAILURE_WAS_READY' }
    $failed.Stop()
    if (@(Get-ChildItem -LiteralPath $failedPath -Filter '*.png').Count) { throw 'FAILED_ACQUISITION_SAVED_IMAGE' }
} finally { $failed.Dispose() }
$slow = [SyntheticVolumeFrames]::Slow((Join-Path $root 'slow'))
try {
    if ($slow.Start(1)) { throw 'EARLY_STARTUP_WAS_READY' }
    $slow.Stop(); $before = $slow.Count
    Start-Sleep -Milliseconds 600
    if ($slow.Count -ne $before) { throw 'TIMED_OUT_OWNER_WROTE_AFTER_JOIN' }
} finally { $slow.Dispose() }
Write-Host 'TWS_DISPLAY_CONTROLS_PASSED: native parse/compile, pixels, clocks, failed and slow startup, no writes after joined stop.'
