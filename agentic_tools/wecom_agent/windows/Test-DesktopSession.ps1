param(
    [string]$OutputPath = 'C:\LabCanvas\Displays\desktop-session.json',
    [string]$ExpectedComputer = 'LABCANVAS-PC'
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) { throw 'Unexpected computer.' }
$session = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
if ($session -eq 0) { throw 'Run through a temporary interactive scheduled task, not SSH session zero.' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DesktopSessionProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int X; public int Y; }
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point point);
    [DllImport("kernel32.dll")] public static extern uint WTSGetActiveConsoleSessionId();
}
'@
[DesktopSessionProbe]::SetProcessDPIAware() | Out-Null
$point = New-Object DesktopSessionProbe+Point
[DesktopSessionProbe]::GetCursorPos([ref]$point) | Out-Null
$os = Get-CimInstance Win32_OperatingSystem
$result = [ordered]@{
    observed_at = [DateTimeOffset]::Now.ToString('o')
    computer = $env:COMPUTERNAME
    boot = $os.LastBootUpTime.ToString('o')
    session_id = $session
    active_console_session_id = [DesktopSessionProbe]::WTSGetActiveConsoleSessionId()
    sm_remotesession = [DesktopSessionProbe]::GetSystemMetrics(0x1000)
    sm_remotecontrol = [DesktopSessionProbe]::GetSystemMetrics(0x2001)
    # These Windows metrics describe RDS/shadowing, not WeCom's private checks.
    proves_wecom_warning_absent = $false
    cursor = @{ x=$point.X; y=$point.Y }
    free_memory_mb = [int]($os.FreePhysicalMemory/1024)
    screens = @([System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
        @{ name=$_.DeviceName; x=$_.Bounds.X; y=$_.Bounds.Y
           width=$_.Bounds.Width; height=$_.Bounds.Height; primary=$_.Primary }
    })
    processes = @(Get-Process WXWork,Weixin,tvnserver,dwm,powershell -ErrorAction SilentlyContinue |
        Select-Object Name,Id,SessionId,@{n='private_mb';e={[int]($_.PrivateMemorySize64/1MB)}})
    display_drivers = @(Get-CimInstance Win32_PnPEntity | Where-Object PNPClass -eq 'Display' |
        Select-Object Name,Status,ConfigManagerErrorCode)
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
