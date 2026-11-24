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
# The old title-only finder rejects these legitimate identity routes. Process
# names and installation-path components are checked independently of the title.
if (![RossDiagnostics.Native]::TwsIdentity('DU_SYNTHETIC', 'SunAwtFrame', 'javaw', 'C:\Jts\tws\jre\bin\javaw.exe')) { throw 'ACCOUNT_ONLY_JAVA_TITLE_REJECTED' }
if (![RossDiagnostics.Native]::TwsIdentity('DU_SYNTHETIC', 'AnyNativeClass', 'tws', 'C:\Apps\tws.exe')) { throw 'NATIVE_TWS_DYNAMIC_TITLE_REJECTED' }
if (![RossDiagnostics.Native]::TwsIdentity('Trader Workstation', 'SunAwtFrame', 'javaw', 'C:\Apps\javaw.exe')) { throw 'EXISTING_TWS_TITLE_ROUTE_REJECTED' }
foreach ($case in @(
    @('Editor','SunAwtFrame','javaw','C:\Apps\editor\javaw.exe'),
    @('Trader Workstation','Chrome_WidgetWin_1','chrome','C:\Apps\chrome.exe'),
    @('IB Gateway','SunAwtFrame','javaw','C:\Jts\ibgateway\javaw.exe'),
    @('Trader Workstation Configuration','SunAwtDialog','javaw','C:\Jts\javaw.exe'),
    @('Editor','SunAwtFrame','javaw','C:\not-jts\javaw.exe')
)) {
    if ([RossDiagnostics.Native]::TwsIdentity($case[0],$case[1],$case[2],$case[3])) { throw 'UNRELATED_OR_CONFIGURATION_WINDOW_ACCEPTED' }
}
$discovery = [RossDiagnostics.Native]::DiscoveryJson() | ConvertFrom-Json
if ($null -eq $discovery.visible_windows -or $null -eq $discovery.supported_tws_windows) { throw 'DISCOVERY_COUNTS_MISSING' }
$serializedDiscovery = $discovery | ConvertTo-Json -Compress
if ($serializedDiscovery -match 'DU_SYNTHETIC|[A-Z]:\\|Trader Workstation|process_id|window_title') { throw 'PRIVATE_DISCOVERY_FIELDS_EXPOSED' }
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
# Exercise the actual native enumerator, including a minimized main window
# whose title does not contain Trader Workstation. This executable is an inert
# test-only form; it imports no broker code and makes no network request.
$fixtureExe = Join-Path $root 'tws.exe'
$windowFixture = @'
using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
public sealed class PassiveOverlay : Form {
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override CreateParams CreateParams {
        get { CreateParams value = base.CreateParams; value.ExStyle |= 0x08000000 | 0x00000080; return value; }
    }
}
public static class InertWindowFixture {
    [STAThread] public static void Main(string[] args) {
        using (Form form = new Form()) {
            form.Text = "dynamic offline fixture";
            form.StartPosition = FormStartPosition.Manual; form.Left = 150; form.Top = 150;
            form.Width = 600; form.Height = 200; form.WindowState = FormWindowState.Minimized;
            form.Shown += delegate { File.WriteAllText(args[0], "READY"); };
            DateTime started = DateTime.UtcNow;
            PassiveOverlay overlay = null;
            using (Timer timer = new Timer()) {
                timer.Interval = 100;
                timer.Tick += delegate {
                    if (File.Exists(args[0] + ".overlay") && overlay == null) {
                        overlay = new PassiveOverlay(); overlay.TopMost = true; overlay.ShowInTaskbar = false;
                        overlay.StartPosition = FormStartPosition.Manual;
                        overlay.FormBorderStyle = FormBorderStyle.None;
                        overlay.Bounds = new Rectangle(form.Left+40, form.Top+60, 120, 40);
                        overlay.BackColor = Color.Blue; overlay.Show();
                        File.WriteAllText(args[0] + ".overlay-ready", "READY");
                    }
                    if (File.Exists(args[0] + ".stop") || (DateTime.UtcNow-started).TotalSeconds > 20) form.Close();
                };
                timer.Start(); Application.Run(form);
            }
            if (overlay != null) overlay.Dispose();
        }
    }
}
'@
Add-Type -TypeDefinition $windowFixture -OutputAssembly $fixtureExe -OutputType WindowsApplication `
    -ReferencedAssemblies @('System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll')
$readyPath = Join-Path $root 'window-ready'
$fixtureProcess = Start-Process -FilePath $fixtureExe -ArgumentList ('"{0}"' -f $readyPath) -PassThru
try {
    $deadline = [datetime]::UtcNow.AddSeconds(10)
    while (!(Test-Path -LiteralPath $readyPath) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (!(Test-Path -LiteralPath $readyPath)) { throw 'INERT_WINDOW_DID_NOT_START' }
    $found = [RossDiagnostics.Native]::FindTws()
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while (($found -eq [IntPtr]::Zero -or ![RossDiagnostics.Native]::IsIconic($found)) -and [datetime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 100
        $found = [RossDiagnostics.Native]::FindTws()
    }
    if ($found -eq [IntPtr]::Zero -or [RossDiagnostics.Native]::WindowProcessId($found) -ne $fixtureProcess.Id -or
        ![RossDiagnostics.Native]::IsIconic($found)) { throw 'MINIMIZED_DYNAMIC_TITLE_DISCOVERY_FAILED' }
    [RossDiagnostics.Native]::RestoreTws($found)
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while ([RossDiagnostics.Native]::IsIconic($found) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if ([RossDiagnostics.Native]::IsIconic($found) -or ![RossDiagnostics.Native]::TwsWindow($found)) { throw 'DISCOVERED_TWS_RESTORE_FAILED' }
    $bounds = New-Object 'RossDiagnostics.Native+RECT'
    if (![RossDiagnostics.Native]::GetWindowRect($found, [ref]$bounds)) { throw 'INERT_WINDOW_GEOMETRY_UNAVAILABLE' }
    $area = [Drawing.Rectangle]::FromLTRB($bounds.Left+50, $bounds.Top+70, $bounds.Left+130, $bounds.Top+90)
    if (![RossDiagnostics.Native]::Unobscured($found, $area)) { throw 'CLEAR_INERT_WINDOW_WAS_OBSCURED' }
    # Wait for the asynchronous restore/foreground transition before establishing
    # the fixture baseline; later changes must not be mistaken for overlay input.
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while ([RossDiagnostics.Native]::GetForegroundWindow() -ne $found -and [datetime]::UtcNow -lt $deadline) {
        $null = [RossDiagnostics.Native]::SetForegroundWindow($found)
        Start-Sleep -Milliseconds 100
    }
    if ([RossDiagnostics.Native]::GetForegroundWindow() -ne $found) { throw 'INERT_OWNER_NOT_FOREGROUND' }
    [IO.File]::WriteAllText($readyPath + '.overlay', 'SHOW')
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while (!(Test-Path -LiteralPath ($readyPath + '.overlay-ready')) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (!(Test-Path -LiteralPath ($readyPath + '.overlay-ready'))) { throw 'PASSIVE_OVERLAY_DID_NOT_START' }
    if ([RossDiagnostics.Native]::GetForegroundWindow() -ne $found) { throw 'PASSIVE_OVERLAY_CHANGED_FOREGROUND' }
    if ([RossDiagnostics.Native]::Unobscured($found, $area)) { throw 'NON_ACTIVATING_OVERLAY_WAS_ACCEPTED' }
} finally {
    [IO.File]::WriteAllText($readyPath + '.stop', 'STOP')
    if (!$fixtureProcess.WaitForExit(3000)) { $fixtureProcess.Kill(); $fixtureProcess.WaitForExit() }
}
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
Write-Host 'TWS_DISPLAY_CONTROLS_PASSED: native parse/compile, minimized dynamic-title discovery/restore, passive overlay refusal, identity negatives, private discovery counts, pixels, clocks, failed/slow startup, joined stop.'
