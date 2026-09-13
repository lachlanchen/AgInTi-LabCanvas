param([switch]$LaunchWeChat, [switch]$Watch, [string]$ExpectedComputer = 'LABCANVAS-PC')
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) { throw 'Unexpected computer; refusing window placement.' }
if ([System.Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
    throw 'Run through an interactive scheduled task, not in the SSH desktop.'
}
Add-Type -AssemblyName System.Windows.Forms
. "$PSScriptRoot\NativeWindows.ps1"
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AppScreens {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int height, uint flags);
}
'@
[AppScreens]::SetProcessDPIAware() | Out-Null
$screens = @([System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.Left })
if ($screens.Count -ne 2 -or $screens[0].Bounds.X -ne 0 -or $screens[1].Bounds.X -ne 1280 -or
    @($screens | Where-Object { $_.Bounds.Width -ne 1280 -or $_.Bounds.Height -ne 800 -or $_.Bounds.Y -ne 0 }).Count -ne 0) {
    throw 'Expected two adjacent 1280x800 monitors, primary at (0,0); refusing guessed coordinates.'
}
if ($LaunchWeChat -and -not (Get-Process WeChat,Weixin -ErrorAction SilentlyContinue)) {
    $paths = @('C:\Program Files\Tencent\Weixin\Weixin.exe','C:\Program Files\Tencent\WeChat\WeChat.exe','C:\Program Files (x86)\Tencent\WeChat\WeChat.exe')
    $exe = $paths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $exe) { throw 'Windows WeChat is not installed.' }
    Start-Process -FilePath $exe
    Start-Sleep -Seconds 5
}
$seen = @{}
$first = $true
do {
    $changed = $false
    $placed = @()
    $live = @{}
    $ids = @(Get-Process WeChat,Weixin -ErrorAction SilentlyContinue | ForEach-Object Id)
    $windows = [LabCanvasDesktop.NativeWindows]::Snapshot([int[]]$ids)
    foreach ($window in $windows) {
        $rect = $window
        if ($rect.Width -lt 200 -or $rect.Height -lt 200) { continue }
        $handle = $window.Handle
        $kind = if ($rect.Width -lt 700) { 'login' } else { 'main' }
        $key = '{0}-{1}-{2}' -f $window.ProcessId,$handle,$kind
        $live[$key] = $true
        if ($seen.ContainsKey($key)) { continue }
        $b = $screens[1].WorkingArea
        if ($kind -eq 'login') {
            $w = [int]$rect.Width; $h = [int]$rect.Height
            $x = $b.X + [int](($b.Width-$w)/2); $y = $b.Y + [int](($b.Height-$h)/2)
        } else { $x=$b.X; $y=$b.Y; $w=$b.Width; $h=$b.Height }
        # No foreground activation and no movement of the existing WeCom UI.
        [AppScreens]::SetWindowPos($handle,[IntPtr]::Zero,$x,$y,$w,$h,0x0014) | Out-Null
        $seen[$key] = $true
        $placed += "WeChat-$kind"
        $changed = $true
    }
    # Keep only currently visible window identities, not years of handle history.
    foreach ($key in @($seen.Keys)) {
        if (-not $live.ContainsKey($key)) { $seen.Remove($key) }
    }
$result = [ordered]@{ observed_at = [DateTimeOffset]::Now.ToString('o'); placed = $placed
    screens = @($screens | ForEach-Object { @{ name=$_.DeviceName; x=$_.Bounds.X; y=$_.Bounds.Y; width=$_.Bounds.Width; height=$_.Bounds.Height; primary=$_.Primary } }) }
if ($first -or $changed) {
    $result | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 C:\LabCanvas\Displays\screens.json
    $first = $false
}
    if ($Watch) { Start-Sleep -Seconds 3 }
} while ($Watch)
