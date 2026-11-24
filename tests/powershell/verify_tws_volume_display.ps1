# Native Windows PowerShell 5.1: compile the actual helper and exercise image
# readiness, write failure, timestamping and joined cleanup. Native image reads
# use only the inert local fixture below; no real TWS, broker or network is used.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$entry = Join-Path $repo 'scripts\certification\capture_tws_volume_display.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($entry, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'AUTOMATIC_DISPLAY_OPERATOR_PARSE_FAILED' }
$interactive = @($ast.FindAll({ param($node)
    ($node -is [Management.Automation.Language.CommandAst] -and
        ($node.GetCommandName() -ceq 'Read-Host' -or $node.Extent.Text -match '\bRegionSelector\b')) -or
    ($node -is [Management.Automation.Language.InvokeMemberExpressionAst] -and
        ($node.Member.Extent.Text -ceq 'ShowDialog' -or $node.Expression.Extent.Text -match '\bMessageBox\b'))
}, $true))
if ($interactive.Count) { throw 'AUTOMATIC_DISPLAY_ENTRY_REQUIRES_MANUAL_SELECTION' }
# Execute the actual passive-listener function and its admission guard under a
# cmdlet stub. This verifies endpoint filtering and PID de-duplication without
# touching a socket, TWS process, real account or unrelated operator setup.
$listenerDefinitions = @($ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -ceq 'Get-VolumeListenerOwners'
}, $true))
$listenerGuards = @($ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.IfStatementAst] -and
    $node.Extent.Text.Contains('UNIQUE_PAPER_API_LISTENER_REQUIRED_NO_CAPTURE_STARTED')
}, $true))
if ($listenerDefinitions.Count -ne 1 -or $listenerGuards.Count -ne 1) { throw 'ACTUAL_LISTENER_CONTRACT_NOT_FOUND' }
$listenerHarness = [ScriptBlock]::Create(@'
param([object[]]$Rows, [bool]$QueryFails = $false)
$listenerState = [pscustomobject]@{ Rows=$Rows; QueryFails=$QueryFails; Calls=0 }
function Get-NetTCPConnection {
    [CmdletBinding()]
    param([string]$State, [int]$LocalPort)
    if ($State -cne 'Listen' -or $LocalPort -ne 7497) { throw 'UNEXPECTED_LISTENER_QUERY' }
    $listenerState.Calls++
    if ($listenerState.QueryFails) { throw 'Synthetic private query failure' }
    $listenerState.Rows
}
'@ + "`n" + $listenerDefinitions[0].Extent.Text + "`n" + @'
try {
    $owners = @(Get-VolumeListenerOwners)
'@ + "`n" + $listenerGuards[0].Extent.Text + "`n" + @'
    [pscustomobject]@{ Owners=$owners; Calls=$listenerState.Calls; Failure=$null }
} catch {
    [pscustomobject]@{ Owners=@(); Calls=$listenerState.Calls; Failure=$_.Exception.Message }
}
'@)
$mixedRows = @(
    [pscustomobject]@{ LocalAddress='127.0.0.1'; OwningProcess=101 },
    [pscustomobject]@{ LocalAddress='0.0.0.0'; OwningProcess=101 },
    [pscustomobject]@{ LocalAddress='::'; OwningProcess=101 },
    [pscustomobject]@{ LocalAddress='::1'; OwningProcess=101 },
    [pscustomobject]@{ LocalAddress='192.0.2.1'; OwningProcess=202 },
    [pscustomobject]@{ LocalAddress='127.0.0.2'; OwningProcess=303 }
)
$listenerResult = & $listenerHarness -Rows $mixedRows
if ($listenerResult.Failure -or $listenerResult.Calls -ne 1 -or
    $listenerResult.Owners.Count -ne 1 -or $listenerResult.Owners[0] -ne 101) { throw 'LISTENER_LOOPBACK_FILTER_OR_DEDUPLICATION_FAILED' }
foreach ($address in @('127.0.0.1','0.0.0.0','::1','::')) {
    $listenerResult = & $listenerHarness -Rows @([pscustomobject]@{ LocalAddress=$address; OwningProcess=101 })
    if ($listenerResult.Failure -or $listenerResult.Owners.Count -ne 1 -or $listenerResult.Owners[0] -ne 101) {
        throw 'SUPPORTED_LISTENER_ADDRESS_REJECTED'
    }
}
$listenerResult = & $listenerHarness -Rows @()
if ($listenerResult.Failure -cne 'UNIQUE_PAPER_API_LISTENER_REQUIRED_NO_CAPTURE_STARTED') { throw 'EMPTY_LISTENER_WAS_ADMITTED' }
foreach ($rows in @(
    @([pscustomobject]@{ LocalAddress='192.0.2.1'; OwningProcess=101 }),
    @([pscustomobject]@{ LocalAddress='127.0.0.1'; OwningProcess=0 }),
    @([pscustomobject]@{ LocalAddress='127.0.0.1'; OwningProcess=101 }, [pscustomobject]@{ LocalAddress='0.0.0.0'; OwningProcess=202 })
)) {
    $listenerResult = & $listenerHarness -Rows $rows
    if ($listenerResult.Failure -cne 'UNIQUE_PAPER_API_LISTENER_REQUIRED_NO_CAPTURE_STARTED') { throw 'MISSING_OR_AMBIGUOUS_LISTENER_WAS_ADMITTED' }
}
$listenerResult = & $listenerHarness -Rows @() -QueryFails $true
if ($listenerResult.Calls -ne 1 -or $listenerResult.Failure -cne 'PAPER_API_LISTENER_QUERY_UNAVAILABLE_NO_NEW_REQUEST') {
    throw 'LISTENER_QUERY_FAILURE_NOT_SANITIZED'
}
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Path (Join-Path $repo 'scripts\certification\TwsVolumeDisplayCapture.cs') -ReferencedAssemblies @(
    'System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll'
)
[RossDiagnostics.Native]::DpiAware()
$desktop = [Drawing.Rectangle]::new(0,0,3840,2160)
foreach ($region in @(
    [Drawing.Rectangle]::new(20,20,1200,600),
    [Drawing.Rectangle]::new(0,0,3840,2160)
)) {
    if (![RossDiagnostics.Native]::ValidClientRegion($region,$desktop)) { throw 'NORMAL_FULL_CLIENT_REGION_REJECTED' }
}
$largeDesktop = [Drawing.Rectangle]::new(0,0,16384,16384)
foreach ($region in @(
    [Drawing.Rectangle]::new(0,0,8192,1024),
    [Drawing.Rectangle]::new(0,0,4096,2048)
)) {
    if (![RossDiagnostics.Native]::ValidClientRegion($region,$largeDesktop)) { throw 'EXACT_CLIENT_PIXEL_LIMIT_REJECTED' }
}
foreach ($region in @(
    [Drawing.Rectangle]::new(0,0,59,20),
    [Drawing.Rectangle]::new(0,0,60,19),
    [Drawing.Rectangle]::new(0,0,8193,20),
    [Drawing.Rectangle]::new(0,0,60,8193),
    [Drawing.Rectangle]::new(0,0,4096,2049),
    [Drawing.Rectangle]::new(0,0,0,100),
    [Drawing.Rectangle]::new(0,0,-1,100)
)) {
    if ([RossDiagnostics.Native]::ValidClientRegion($region,$largeDesktop)) { throw 'INVALID_CLIENT_DIMENSIONS_OR_PIXELS_ACCEPTED' }
}
foreach ($region in @(
    [Drawing.Rectangle]::new(-1,0,1200,600),
    [Drawing.Rectangle]::new(3500,1800,1200,600)
)) {
    if ([RossDiagnostics.Native]::ValidClientRegion($region,$desktop)) { throw 'OFFSCREEN_CLIENT_REGION_ACCEPTED' }
}
$negativeDesktop = [Drawing.Rectangle]::new(-1920,0,3840,2160)
if (![RossDiagnostics.Native]::ValidClientRegion([Drawing.Rectangle]::new(-1800,20,1200,600),$negativeDesktop)) {
    throw 'VALID_NEGATIVE_MONITOR_ORIGIN_REJECTED'
}
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
using System.Runtime.InteropServices;
using System.Windows.Forms;
public sealed class PassiveOverlay : Form {
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override CreateParams CreateParams {
        get { CreateParams value = base.CreateParams; value.ExStyle |= 0x08000000 | 0x00000080; return value; }
    }
}
public static class InertWindowFixture {
    [DllImport("dwmapi.dll")] static extern int DwmFlush();
    [STAThread] public static void Main(string[] args) {
        using (Form form = new Form()) {
            form.Text = "dynamic offline fixture";
            form.StartPosition = FormStartPosition.Manual; form.Left = 20; form.Top = 20;
            form.Width = 600; form.Height = 600; form.BackColor = Color.Red;
            form.WindowState = FormWindowState.Minimized;
            form.Shown += delegate { File.WriteAllText(args[0], "READY"); };
            DateTime started = DateTime.UtcNow;
            bool paintRequested = false;
            PassiveOverlay overlay = null;
            using (Timer timer = new Timer()) {
                timer.Interval = 100;
                timer.Tick += delegate {
                    if (form.WindowState == FormWindowState.Normal && !File.Exists(args[0] + ".painted")) {
                        if (!paintRequested) { form.Refresh(); form.Update(); DwmFlush(); paintRequested = true; }
                        else File.WriteAllText(args[0] + ".painted", "READY");
                    }
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
    # A supported TWS fixture exists, so these refusals prove there is no global
    # fallback when the expected API-listener PID is missing or belongs elsewhere.
    if ([RossDiagnostics.Native]::FindTwsForProcess(0) -ne [IntPtr]::Zero) { throw 'MISSING_LISTENER_PID_ACCEPTED' }
    if ([RossDiagnostics.Native]::FindTwsForProcess([uint32]$PID) -ne [IntPtr]::Zero) { throw 'UNRELATED_LISTENER_PID_ACCEPTED' }
    $found = [RossDiagnostics.Native]::FindTwsForProcess([uint32]$fixtureProcess.Id)
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while (($found -eq [IntPtr]::Zero -or ![RossDiagnostics.Native]::IsIconic($found)) -and [datetime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 100
        $found = [RossDiagnostics.Native]::FindTwsForProcess([uint32]$fixtureProcess.Id)
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
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while (!(Test-Path -LiteralPath ($readyPath + '.painted')) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (!(Test-Path -LiteralPath ($readyPath + '.painted'))) { throw 'INERT_CLIENT_DID_NOT_PAINT' }
    $client = [RossDiagnostics.Native]::ClientRegion($found)
    if ($client.Height -le 400 -or $client.Width -lt 60 -or
        $client.X -le $bounds.Left -or $client.Y -le $bounds.Top -or
        $client.Width -ge $bounds.Rectangle.Width -or $client.Height -ge $bounds.Rectangle.Height) {
        throw 'AUTOMATIC_CLIENT_GEOMETRY_INCLUDES_BORDER_OR_OLD_CROP_LIMIT'
    }
    if (![RossDiagnostics.Native]::ValidClientRegion($client,[System.Windows.Forms.SystemInformation]::VirtualScreen)) {
        throw 'INERT_CLIENT_IS_OUTSIDE_CAPTURE_DESKTOP'
    }
    $legacyRejected = $false
    try {
        $legacy = [RossDiagnostics.VolumeDisplayRecorder]::FromScreen((Join-Path $root 'legacy-full-client'), $found, $client)
        $legacy.Dispose()
    } catch { $legacyRejected = $true }
    if (!$legacyRejected) { throw 'CROPPED_FACTORY_LOST_ITS_EXISTING_DIMENSION_CAP' }
    $fullPath = Join-Path $root 'full-client'
    $full = [RossDiagnostics.VolumeDisplayRecorder]::FromWindow($fullPath,$found)
    try {
        if (!$full.Start(3000)) { throw 'AUTOMATIC_FULL_CLIENT_NOT_READY' }
        $full.Stop()
        if ($full.Failure -or $full.Count -lt 1) { throw 'AUTOMATIC_FULL_CLIENT_FAILED' }
        $fullRows = @(Get-Content -LiteralPath (Join-Path $fullPath 'frames.jsonl') | ForEach-Object { $_ | ConvertFrom-Json })
        if ($fullRows.Count -ne $full.Count) { throw 'FULL_CLIENT_MANIFEST_COUNT_MISMATCH' }
        foreach ($row in $fullRows) {
            if ([datetimeoffset]::Parse($row.started_utc) -gt [datetimeoffset]::Parse($row.finished_utc)) { throw 'FULL_CLIENT_FRAME_CLOCK_ORDER_FAILED' }
            $image = [Drawing.Bitmap]::FromFile((Join-Path $fullPath $row.file))
            try {
                if ($image.Width -ne $client.Width -or $image.Height -ne $client.Height -or
                    $image.GetPixel(1,1).ToArgb() -ne [Drawing.Color]::Red.ToArgb() -or
                    $image.GetPixel([int]($image.Width/2),[int]($image.Height/2)).ToArgb() -ne [Drawing.Color]::Red.ToArgb()) {
                    throw 'FULL_CLIENT_PIXELS_OR_DIMENSIONS_DIFFER'
                }
            } finally { $image.Dispose() }
        }
    } finally { $full.Dispose() }
    [IO.File]::WriteAllText($readyPath + '.overlay', 'SHOW')
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while (!(Test-Path -LiteralPath ($readyPath + '.overlay-ready')) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (!(Test-Path -LiteralPath ($readyPath + '.overlay-ready'))) { throw 'PASSIVE_OVERLAY_DID_NOT_START' }
    # Establish the review's actual capture-time condition: the owner is
    # foreground while an unowned topmost window still covers its selected area.
    # Form.Show can transiently change activation even with NOACTIVATE requested.
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while ([RossDiagnostics.Native]::GetForegroundWindow() -ne $found -and [datetime]::UtcNow -lt $deadline) {
        $null = [RossDiagnostics.Native]::SetForegroundWindow($found)
        Start-Sleep -Milliseconds 100
    }
    if ([RossDiagnostics.Native]::GetForegroundWindow() -ne $found) { throw 'OCCLUDED_OWNER_NOT_FOREGROUND' }
    if ([RossDiagnostics.Native]::Unobscured($found, $area)) { throw 'NON_ACTIVATING_OVERLAY_WAS_ACCEPTED' }
    $occluded = [RossDiagnostics.VolumeDisplayRecorder]::FromScreen((Join-Path $root 'occluded'), $found, $area)
    try {
        if ($occluded.Start(3000) -or $occluded.Count -ne 0) { throw 'OCCLUDED_FRAME_WRITTEN' }
        $occluded.Stop()
        if ($occluded.Failure -cne 'InvalidOperationException') { throw 'OCCLUSION_REFUSAL_NOT_RETAINED' }
    } finally { $occluded.Dispose() }
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
Write-Host 'TWS_DISPLAY_CONTROLS_PASSED: no manual-selection entry, listener-PID binding, minimized dynamic-title discovery/restore, full client geometry/pixels/times and caps, passive overlay refusal, private discovery counts, failed/slow startup, joined stop.'
