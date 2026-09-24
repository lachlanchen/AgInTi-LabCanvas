# Plain value snapshots avoid retaining UI Automation providers in long-lived helpers.
if ('LabCanvasDesktop.NativeWindows' -as [type]) { return }
Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace LabCanvasDesktop {
    public sealed class WindowInfo {
        public IntPtr Handle;
        public int ProcessId, X, Y, Width, Height;
        public string Name, ClassName;
    }
    public static class NativeWindows {
        private delegate bool EnumProc(IntPtr window, IntPtr arg);
        [StructLayout(LayoutKind.Sequential)]
        private struct Rect { public int Left, Top, Right, Bottom; }
        [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc proc, IntPtr arg);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr window);
        [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr window, uint command);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
        [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr window, out Rect rect);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)]
        private static extern int GetClassName(IntPtr window, StringBuilder text, int count);
        [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();

        public static bool IsAbove(IntPtr candidate, IntPtr target) {
            var seen = new HashSet<IntPtr>();
            // GW_HWNDPREV follows documented Z order. Bound traversal in case
            // windows are destroyed/reordered while the helper observes them.
            for (IntPtr current = GetWindow(target, 3); current != IntPtr.Zero;
                 current = GetWindow(current, 3)) {
                if (!seen.Add(current) || seen.Count > 4096)
                    throw new InvalidOperationException("Window order changed during capture.");
                if (current == candidate) return true;
            }
            return false;
        }

        public static WindowInfo[] Snapshot(int[] processIds) {
            return Snapshot(processIds, false);
        }

        public static WindowInfo[] Snapshot(int[] processIds, bool includeHidden) {
            var result = new List<WindowInfo>();
            var allowed = new HashSet<int>(processIds);
            if (allowed.Count == 0) return result.ToArray();
            EnumWindows(delegate(IntPtr handle, IntPtr arg) {
                uint pid;
                GetWindowThreadProcessId(handle, out pid);
                if (!allowed.Contains((int)pid) || (!includeHidden && (!IsWindowVisible(handle) || IsIconic(handle)))) return true;
                Rect rect;
                if (!GetWindowRect(handle, out rect)) return true;
                var name = new StringBuilder(512);
                var cls = new StringBuilder(256);
                GetWindowText(handle, name, name.Capacity);
                GetClassName(handle, cls, cls.Capacity);
                result.Add(new WindowInfo { Handle=handle, ProcessId=(int)pid,
                    X=rect.Left, Y=rect.Top, Width=rect.Right-rect.Left, Height=rect.Bottom-rect.Top,
                    Name=name.ToString(), ClassName=cls.ToString() });
                return true;
            }, IntPtr.Zero);
            return result.ToArray();
        }
    }
}
'@
[LabCanvasDesktop.NativeWindows]::SetProcessDPIAware() | Out-Null
