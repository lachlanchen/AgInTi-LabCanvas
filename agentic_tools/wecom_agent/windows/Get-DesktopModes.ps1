param([string]$OutputPath = 'C:\LabCanvas\Displays\modes.json')
$ErrorActionPreference = 'Stop'
if ([System.Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
    throw 'Display modes must be read from the interactive desktop.'
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DesktopModes {
    // Display form of DEVMODEW: the printer union is replaced by its display fields.
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct Mode {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string DeviceName;
        public ushort SpecVersion, DriverVersion, Size, DriverExtra;
        public uint Fields;
        public int X, Y;
        public uint Orientation, FixedOutput;
        public short Color, Duplex, YResolution, TTOption, Collate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string FormName;
        public ushort LogPixels;
        public uint BitsPerPel, Width, Height, Flags, Frequency;
        public uint ICMMethod, ICMIntent, MediaType, DitherType, Reserved1, Reserved2;
        public uint PanningWidth, PanningHeight;
    }
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern bool EnumDisplaySettings(string device, int index, ref Mode mode);
}
'@
$result = foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) {
    $modes = for ($i=0; ; $i++) {
        $mode = New-Object DesktopModes+Mode
        $mode.Size = [Runtime.InteropServices.Marshal]::SizeOf($mode)
        if (-not [DesktopModes]::EnumDisplaySettings($screen.DeviceName,$i,[ref]$mode)) { break }
        [ordered]@{ width=$mode.Width; height=$mode.Height; hz=$mode.Frequency; bpp=$mode.BitsPerPel }
    }
    [ordered]@{ device=$screen.DeviceName; primary=$screen.Primary; modes=@($modes) }
}
$result | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath
