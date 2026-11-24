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
        // uses FromScreen, which binds a visible TWS window and selected rectangle.
        public VolumeDisplayRecorder(string directory, Func<Bitmap> read) {
            this.directory = directory;
            this.read = read;
        }
        public static VolumeDisplayRecorder FromScreen(string directory, IntPtr owner, Rectangle region) {
            Native.RECT original;
            if (!Native.GetWindowRect(owner, out original) || !Native.TwsWindow(owner)
                || !original.Rectangle.Contains(region) || region.Width < 60 || region.Height < 20
                || region.Width > 2400 || region.Height > 400)
                throw new InvalidOperationException("TWS_DISPLAY_SCOPE_REQUIRED");
            return new VolumeDisplayRecorder(directory, delegate {
                Native.RECT current;
                if (!Native.TwsWindow(owner) || Native.IsIconic(owner)
                    || !Native.GetWindowRect(owner, out current) || current.Rectangle != original.Rectangle
                    || Native.GetAncestor(Native.GetForegroundWindow(), 2) != owner)
                    throw new InvalidOperationException("TWS_DISPLAY_MOVED_OR_OBSCURED");
                Bitmap image = new Bitmap(region.Width, region.Height, PixelFormat.Format24bppRgb);
                try {
                    using (Graphics g = Graphics.FromImage(image)) {
                        g.CopyFromScreen(region.Location, Point.Empty, region.Size, CopyPixelOperation.SourceCopy);
                    }
                    // A focus or geometry change during acquisition invalidates it.
                    if (!Native.GetWindowRect(owner, out current) || current.Rectangle != original.Rectangle
                        || Native.GetAncestor(Native.GetForegroundWindow(), 2) != owner)
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
                            image.Save(Path.Combine(directory, name), ImageFormat.Png);
                            bytes += new FileInfo(Path.Combine(directory, name)).Length;
                            log.WriteLine("{\"started_utc\":\"" + began + "\",\"finished_utc\":\"" + ended
                                + "\",\"file\":\"" + name + "\"}");
                            Interlocked.Increment(ref count);
                            ready.Set();
                            if (bytes > 67108864) { failure = "CAPTURE_BYTE_LIMIT"; break; }
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
        [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(Point point);
        [DllImport("user32.dll")] static extern bool ShowWindowAsync(IntPtr window, int command);
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out RECT rectangle);
        [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr window);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr window, uint flags);
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
        [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
        public static void DpiAware() { SetProcessDPIAware(); }
        public static uint WindowProcessId(IntPtr window) { uint id; GetWindowThreadProcessId(window, out id); return id; }
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
            if (IsIconic(window)) ShowWindowAsync(window, 9);
            SetForegroundWindow(window);
        }
        public static IntPtr WindowForRegion(Rectangle region) {
            IntPtr window = GetAncestor(WindowFromPoint(new Point(region.X + region.Width/2, region.Y + region.Height/2)), 2);
            RECT bounds;
            if (TwsWindow(window) && !IsIconic(window) && GetWindowRect(window, out bounds)
                && bounds.Rectangle.Contains(region)) return window;
            // Closing the selector can return focus to the terminal. Resolve a
            // unique supported TWS under the selected rectangle, then restore it.
            IntPtr selected = IntPtr.Zero; int matches = 0;
            EnumWindows(delegate(IntPtr candidate, IntPtr ignored) {
                RECT rectangle;
                if (TwsWindow(candidate) && !IsIconic(candidate) && GetWindowRect(candidate, out rectangle)
                    && rectangle.Rectangle.Contains(region)) { selected = candidate; matches++; }
                return true;
            }, IntPtr.Zero);
            if (matches != 1) throw new InvalidOperationException("SELECTED_REGION_IS_NOT_A_UNIQUE_SUPPORTED_TWS_WINDOW");
            RestoreTws(selected);
            return selected;
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
        public static IntPtr FindTws() {
            IntPtr found = IntPtr.Zero; long area = 0;
            EnumWindows(delegate(IntPtr window, IntPtr unused) {
                RECT rect;
                if (TwsWindow(window) && GetWindowRect(window, out rect)) {
                    long candidate = (long)rect.Rectangle.Width * rect.Rectangle.Height;
                    if (candidate > area) { area = candidate; found = window; }
                }
                return true;
            }, IntPtr.Zero);
            return found;
        }
    }

    // One drag chooses only the watchlist header and LGHL row. The temporary
    // background stays in memory; only the chosen region is ever saved.
    public sealed class RegionSelector : Form {
        readonly Bitmap background;
        readonly Point origin;
        Point anchor;
        Rectangle selected;
        bool dragging;
        public Rectangle Selected { get { return new Rectangle(selected.X + origin.X, selected.Y + origin.Y, selected.Width, selected.Height); } }
        public RegionSelector() {
            Rectangle desktop = SystemInformation.VirtualScreen;
            origin = desktop.Location;
            background = new Bitmap(desktop.Width, desktop.Height);
            using (Graphics g = Graphics.FromImage(background))
                g.CopyFromScreen(desktop.Location, Point.Empty, desktop.Size);
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            Bounds = desktop; TopMost = true; KeyPreview = true; DoubleBuffered = true;
            Cursor = Cursors.Cross;
            KeyDown += delegate(object sender, KeyEventArgs e) { if (e.KeyCode == Keys.Escape) { DialogResult = DialogResult.Cancel; Close(); } };
            MouseDown += delegate(object sender, MouseEventArgs e) { if (e.Button == MouseButtons.Left) { anchor = e.Location; dragging = true; } };
            MouseMove += delegate(object sender, MouseEventArgs e) {
                if (!dragging) return;
                selected = Rectangle.FromLTRB(Math.Min(anchor.X,e.X),Math.Min(anchor.Y,e.Y),Math.Max(anchor.X,e.X),Math.Max(anchor.Y,e.Y));
                Invalidate();
            };
            MouseUp += delegate(object sender, MouseEventArgs e) {
                if (!dragging || e.Button != MouseButtons.Left) return;
                dragging = false;
                if (selected.Width >= 60 && selected.Height >= 20) { DialogResult = DialogResult.OK; Close(); }
            };
        }
        protected override void OnPaint(PaintEventArgs e) {
            e.Graphics.DrawImageUnscaled(background, 0, 0);
            using (Pen pen = new Pen(Color.Red, 3)) e.Graphics.DrawRectangle(pen, selected);
            using (Brush brush = new SolidBrush(Color.Black)) e.Graphics.FillRectangle(brush,0,0,Width,35);
            e.Graphics.DrawString("Drag around the watchlist headers and LGHL row (include full Volume). Esc cancels.", SystemFonts.DefaultFont, Brushes.White, 10, 10);
        }
        protected override void Dispose(bool disposing) { if (disposing) background.Dispose(); base.Dispose(disposing); }
    }
}
