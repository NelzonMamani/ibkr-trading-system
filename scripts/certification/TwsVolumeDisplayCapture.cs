// READ_ONLY visual evidence. No broker API, keyboard input, OCR or unit authority.
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace RossDiagnostics {
    public sealed class VolumeDisplayRecorder : IDisposable {
        public sealed class Frame {
            public string StartedUtc;
            public string FinishedUtc;
            public string File;
        }
        readonly string directory;
        readonly Func<Bitmap> read;
        readonly ManualResetEvent ready = new ManualResetEvent(false);
        readonly ManualResetEvent stop = new ManualResetEvent(false);
        Thread worker;
        volatile string failure;
        int count;
        public string Failure { get { return failure; } }
        public int Count { get { return count; } }

        // A synthetic reader is for native offline verification only. The operator
        // uses FromWindow, which binds the supported TWS client's visible area.
        public VolumeDisplayRecorder(string directory, Func<Bitmap> read) {
            this.directory = directory;
            this.read = read;
        }
        public static VolumeDisplayRecorder FromScreen(string directory, IntPtr owner, Rectangle region) {
            if (region.Width > 2400 || region.Height > 400)
                throw new InvalidOperationException("TWS_DISPLAY_SCOPE_REQUIRED");
            return FromRegion(directory, owner, region, false);
        }
        public static VolumeDisplayRecorder FromWindow(string directory, IntPtr owner) {
            return FromRegion(directory, owner, Native.ClientRegion(owner), true);
        }
        static VolumeDisplayRecorder FromRegion(string directory, IntPtr owner, Rectangle region, bool clientArea) {
            Native.RECT original;
            if (!Native.GetWindowRect(owner, out original) || !Native.TwsWindow(owner)
                || !original.Rectangle.Contains(region) || !Native.ValidClientRegion(region, SystemInformation.VirtualScreen))
                throw new InvalidOperationException("TWS_DISPLAY_SCOPE_REQUIRED");
            return new VolumeDisplayRecorder(directory, delegate {
                Native.RECT current;
                if (!Native.TwsWindow(owner) || Native.IsIconic(owner)
                    || !Native.GetWindowRect(owner, out current) || current.Rectangle != original.Rectangle
                    || (clientArea && Native.ClientRegion(owner) != region)
                    || Native.GetAncestor(Native.GetForegroundWindow(), 2) != owner
                    || !Native.Unobscured(owner, region))
                    throw new InvalidOperationException("TWS_DISPLAY_MOVED_OR_OBSCURED");
                Bitmap image = new Bitmap(region.Width, region.Height, PixelFormat.Format24bppRgb);
                try {
                    using (Graphics g = Graphics.FromImage(image)) {
                        g.CopyFromScreen(region.Location, Point.Empty, region.Size, CopyPixelOperation.SourceCopy);
                    }
                    // A focus or geometry change during acquisition invalidates it.
                    if (!Native.GetWindowRect(owner, out current) || current.Rectangle != original.Rectangle
                        || (clientArea && Native.ClientRegion(owner) != region)
                        || Native.GetAncestor(Native.GetForegroundWindow(), 2) != owner
                        || !Native.Unobscured(owner, region))
                        throw new InvalidOperationException("TWS_DISPLAY_CHANGED_DURING_CAPTURE");
                    return image;
                } catch { image.Dispose(); throw; }
            });
        }
        public bool Start(int timeoutMilliseconds) {
            if (worker != null) throw new InvalidOperationException("RECORDER_ALREADY_STARTED");
            if (Directory.Exists(directory)) throw new InvalidOperationException("NEW_CAPTURE_DIRECTORY_REQUIRED");
            Directory.CreateDirectory(directory);
            worker = new Thread(Run);
            worker.IsBackground = true;
            worker.Start();
            return ready.WaitOne(timeoutMilliseconds) && failure == null && count > 0;
        }
        void Run() {
            try {
                using (StreamWriter log = new StreamWriter(Path.Combine(directory, "frames.jsonl"), false, new UTF8Encoding(false))) {
                    log.AutoFlush = true;
                    long bytes = 0;
                    while (!stop.WaitOne(0) && count < 600) {
                        string began = DateTimeOffset.UtcNow.ToString("o");
                        using (Bitmap image = read()) {
                            if (image == null) throw new InvalidOperationException("DISPLAY_IMAGE_UNAVAILABLE");
                            string ended = DateTimeOffset.UtcNow.ToString("o");
                            string name = "frame-" + count.ToString("D4") + ".png";
                            using (MemoryStream encoded = new MemoryStream()) {
                                image.Save(encoded, ImageFormat.Png);
                                if (encoded.Length > 67108864 - bytes) { failure = "CAPTURE_BYTE_LIMIT"; break; }
                                encoded.Position = 0;
                                using (FileStream saved = new FileStream(Path.Combine(directory, name), FileMode.CreateNew, FileAccess.Write)) {
                                    encoded.CopyTo(saved);
                                }
                                bytes += encoded.Length;
                            }
                            log.WriteLine("{\"started_utc\":\"" + began + "\",\"finished_utc\":\"" + ended
                                + "\",\"file\":\"" + name + "\"}");
                            Interlocked.Increment(ref count);
                            ready.Set();
                        }
                        if (stop.WaitOne(500)) break;
                    }
                    if (count >= 600 && !stop.WaitOne(0)) failure = "CAPTURE_FRAME_LIMIT";
                }
            } catch (Exception ex) { failure = ex.GetType().Name; ready.Set(); }
        }
        public void Stop() {
            stop.Set();
            if (worker != null && !worker.Join(10000)) throw new InvalidOperationException("DISPLAY_RECORDER_STILL_RUNNING");
        }
        public void Dispose() { Stop(); ready.Dispose(); stop.Dispose(); }
    }

    public static class Native {
        [StructLayout(LayoutKind.Sequential)] public struct RECT {
            public int Left, Top, Right, Bottom;
            public Rectangle Rectangle { get { return System.Drawing.Rectangle.FromLTRB(Left, Top, Right, Bottom); } }
        }
        public delegate bool Enumerate(IntPtr window, IntPtr ignored);
        [DllImport("user32.dll")] static extern bool EnumWindows(Enumerate callback, IntPtr ignored);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr window, StringBuilder title, int length);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr window, StringBuilder name, int length);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
        [DllImport("user32.dll")] static extern bool ShowWindowAsync(IntPtr window, int command);
        [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr window, uint command);
        [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr window, int attribute, out int value, int size);
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out RECT rectangle);
        [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr window, out RECT rectangle);
        [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr window, ref Point point);
        [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr window);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr window, uint flags);
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
        [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
        public static void DpiAware() { SetProcessDPIAware(); }
        public static uint WindowProcessId(IntPtr window) { uint id; GetWindowThreadProcessId(window, out id); return id; }
        public static bool ValidClientRegion(Rectangle region, Rectangle desktop) {
            return region.Width >= 60 && region.Height >= 20 && region.Width <= 8192 && region.Height <= 8192
                && (long)region.Width * region.Height <= 8388608 && desktop.Contains(region);
        }
        public static Rectangle ClientRegion(IntPtr window) {
            RECT client, outer;
            Point origin = Point.Empty;
            if (!TwsWindow(window) || IsIconic(window) || !GetClientRect(window, out client)
                || !ClientToScreen(window, ref origin) || !GetWindowRect(window, out outer))
                throw new InvalidOperationException("TWS_CLIENT_AREA_UNAVAILABLE");
            Rectangle region = new Rectangle(origin.X, origin.Y, client.Right-client.Left, client.Bottom-client.Top);
            if (!ValidClientRegion(region, SystemInformation.VirtualScreen) || !outer.Rectangle.Contains(region))
                throw new InvalidOperationException("TWS_CLIENT_AREA_OUT_OF_BOUNDS");
            return region;
        }
        public static bool Unobscured(IntPtr owner, Rectangle region) {
            // Walk windows above this exact owner in Z order, not just the
            // foreground window. Non-activating topmost notifications matter too.
            System.Collections.Generic.Dictionary<IntPtr, bool> seen = new System.Collections.Generic.Dictionary<IntPtr, bool>();
            IntPtr above = GetWindow(owner, 3); // GW_HWNDPREV
            while (above != IntPtr.Zero) {
                if (seen.ContainsKey(above) || seen.Count >= 4096) return false;
                seen.Add(above, true);
                RECT rect;
                int cloaked = 0;
                bool hiddenByDwm = DwmGetWindowAttribute(above, 14, out cloaked, sizeof(int)) == 0 && cloaked != 0;
                if (IsWindowVisible(above) && !IsIconic(above) && !hiddenByDwm) {
                    if (!GetWindowRect(above, out rect) || rect.Rectangle.IntersectsWith(region)) return false;
                }
                above = GetWindow(above, 3);
            }
            return true;
        }
        public static bool TwsIdentity(string title, string className, string processName, string imagePath) {
            title = title ?? ""; className = className ?? "";
            processName = (processName ?? "").ToLowerInvariant(); imagePath = imagePath ?? "";
            if (title.IndexOf("Configuration", StringComparison.OrdinalIgnoreCase) >= 0
                || title.IndexOf("IB Gateway", StringComparison.OrdinalIgnoreCase) >= 0) return false;
            if (processName == "tws" || processName == "tws.exe") return true;
            if ((processName != "java" && processName != "javaw")
                || !className.Equals("SunAwtFrame", StringComparison.Ordinal)) return false;
            bool named = title.IndexOf("Trader Workstation", StringComparison.OrdinalIgnoreCase) >= 0;
            return named || TwsImagePath(imagePath);
        }
        static bool TwsImagePath(string imagePath) {
            string path = (imagePath ?? "").Replace('/', '\\').ToLowerInvariant();
            if (path.Contains("\\ibgateway\\") || path.Contains("\\ib gateway\\")) return false;
            return path.Contains("\\jts\\") || path.Contains("\\tws\\") || path.Contains("\\trader workstation\\");
        }
        static void Identity(IntPtr window, out string title, out string className, out string processName, out string imagePath) {
            StringBuilder text = new StringBuilder(1024); GetWindowText(window, text, text.Capacity); title = text.ToString();
            text = new StringBuilder(256); GetClassName(window, text, text.Capacity); className = text.ToString();
            processName = ""; imagePath = "";
            try {
                uint id; GetWindowThreadProcessId(window, out id);
                using (Process process = Process.GetProcessById(checked((int)id))) {
                    processName = process.ProcessName;
                    try { imagePath = process.MainModule.FileName; } catch { }
                }
            } catch { }
        }
        public static bool TwsWindow(IntPtr window) {
            if (!IsWindowVisible(window)) return false;
            string title, className, processName, imagePath;
            Identity(window, out title, out className, out processName, out imagePath);
            return TwsIdentity(title, className, processName, imagePath);
        }
        public static void RestoreTws(IntPtr window) {
            if (!TwsWindow(window)) throw new InvalidOperationException("TWS_WINDOW_IDENTITY_REQUIRED");
            if (IsIconic(window)) {
                ShowWindowAsync(window, 9);
                Stopwatch wait = Stopwatch.StartNew();
                while (IsIconic(window) && wait.ElapsedMilliseconds < 2000) Thread.Sleep(25);
                if (IsIconic(window)) throw new InvalidOperationException("TWS_RESTORE_NOT_COMPLETE");
            }
            SetForegroundWindow(window);
        }
        public static string DiscoveryJson() {
            int visible = 0, matched = 0, minimized = 0, javaFrames = 0, namedTws = 0, nativeNames = 0, pathMatches = 0;
            EnumWindows(delegate(IntPtr window, IntPtr ignored) {
                if (!IsWindowVisible(window)) return true;
                visible++;
                string title, className, processName, imagePath;
                Identity(window, out title, out className, out processName, out imagePath);
                if (className == "SunAwtFrame") javaFrames++;
                if (title.IndexOf("Trader Workstation", StringComparison.OrdinalIgnoreCase) >= 0) namedTws++;
                if (processName.Equals("tws", StringComparison.OrdinalIgnoreCase)) nativeNames++;
                if (TwsImagePath(imagePath)) pathMatches++;
                if (TwsIdentity(title, className, processName, imagePath)) { matched++; if (IsIconic(window)) minimized++; }
                return true;
            }, IntPtr.Zero);
            // Counts only: never serialize titles, account IDs, handles, PIDs or paths.
            return "{\"visible_windows\":" + visible + ",\"supported_tws_windows\":" + matched
                + ",\"minimized_tws_windows\":" + minimized + ",\"java_frame_windows\":" + javaFrames
                + ",\"title_rule_matches\":" + namedTws + ",\"native_tws_process_windows\":" + nativeNames
                + ",\"installation_path_matches\":" + pathMatches + "}";
        }
        public static IntPtr FindTwsForProcess(uint expectedProcessId) {
            if (expectedProcessId == 0) return IntPtr.Zero;
            IntPtr found = IntPtr.Zero; long area = 0;
            EnumWindows(delegate(IntPtr window, IntPtr unused) {
                RECT rect;
                if (WindowProcessId(window) == expectedProcessId && TwsWindow(window) && GetWindowRect(window, out rect)) {
                    long candidate = (long)rect.Rectangle.Width * rect.Rectangle.Height;
                    if (candidate > area) { area = candidate; found = window; }
                }
                return true;
            }, IntPtr.Zero);
            return found;
        }
    }

}
