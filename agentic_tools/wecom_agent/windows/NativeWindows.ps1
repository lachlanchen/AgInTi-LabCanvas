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
        [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr parent, EnumProc proc, IntPtr arg);
        [DllImport("user32.dll")] private static extern int GetDlgCtrlID(IntPtr window);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr window);
        [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr window);
        [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr window, uint command);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
        [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr window, out Rect rect);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)]
        private static extern int GetClassName(IntPtr window, StringBuilder text, int count);
        [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
        [DllImport("user32.dll", SetLastError=true)]
        private static extern bool PostMessage(IntPtr window, uint message, UIntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
        private static extern IntPtr SendMessageTimeout(IntPtr window, uint message,
            UIntPtr wParam, IntPtr lParam, uint flags, uint timeout, out IntPtr result);

        public static bool IsResponding(IntPtr window) {
            IntPtr result;
            // WM_NULL checks the app's message loop without typing or changing UI.
            return SendMessageTimeout(window, 0, UIntPtr.Zero, IntPtr.Zero,
                2, 2000, out result) != IntPtr.Zero;
        }

        public static IntPtr UniqueChildControl(IntPtr parent, int id, string className) {
            var matches = new List<IntPtr>();
            EnumChildWindows(parent, delegate(IntPtr child, IntPtr arg) {
                var cls = new StringBuilder(256);
                GetClassName(child, cls, cls.Capacity);
                if (GetDlgCtrlID(child) == id && cls.ToString() == className) matches.Add(child);
                return true;
            }, IntPtr.Zero);
            return matches.Count == 1 ? matches[0] : IntPtr.Zero;
        }

        public static string ReadControlText(IntPtr control) {
            IntPtr memory = Marshal.AllocHGlobal(8192);
            try {
                Marshal.WriteInt16(memory, 0);
                IntPtr result;
                if (SendMessageTimeout(control, 0x000D, new UIntPtr(4096), memory, 2, 2000, out result) == IntPtr.Zero)
                    throw new InvalidOperationException("Filename control did not respond.");
                return Marshal.PtrToStringUni(memory);
            } finally { Marshal.FreeHGlobal(memory); }
        }

        public static void FocusDialogControl(IntPtr dialog, IntPtr control) {
            IntPtr result;
            // WM_NEXTDLGCTL updates the common dialog's keyboard focus normally.
            if (SendMessageTimeout(dialog, 0x0028, new UIntPtr((ulong)control.ToInt64()),
                    new IntPtr(1), 2, 2000, out result) == IntPtr.Zero)
                throw new InvalidOperationException("Save As filename control could not be focused.");
        }

        public static void CancelDialog(IntPtr dialog) {
            if (!PostMessage(dialog, 0x0010, UIntPtr.Zero, IntPtr.Zero))
                throw new InvalidOperationException("File export dialog could not be cancelled.");
        }

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
