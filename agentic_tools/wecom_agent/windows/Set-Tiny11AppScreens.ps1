param(
    [switch]$LaunchWeChat,
    [switch]$Watch,
    [ValidateSet('Dual', 'Shared')][string]$Layout = 'Dual',
    [string]$ExpectedComputer = 'LABCANVAS-PC'
)
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
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect {
        public int Left, Top, Right, Bottom;
        public int X { get { return Left; } }
        public int Y { get { return Top; } }
        public int Width { get { return Right-Left; } }
        public int Height { get { return Bottom-Top; } }
    }
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int height, uint flags);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr window, uint command);
    [DllImport("user32.dll", EntryPoint="GetWindowLongW")]
    private static extern int GetWindowLong(IntPtr window, int index);
    public static bool IsMainWindow(IntPtr window) {
        return GetWindow(window, 4) == IntPtr.Zero && (GetWindowLong(window, -16) & 0x10000) != 0;
    }
    [DllImport("user32.dll")]
    private static extern bool SystemParametersInfo(uint action, uint param, out Rect rect, uint flags);
    public static Rect PrimaryWorkingArea() {
        Rect rect;
        if (!SystemParametersInfo(48, 0, out rect, 0))
            throw new InvalidOperationException("Primary working area unavailable.");
        return rect;
    }
}
'@
[AppScreens]::SetProcessDPIAware() | Out-Null
$screens = @([System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.Left })
$primary = [System.Windows.Forms.Screen]::PrimaryScreen
if ($Layout -eq 'Shared') {
    if ($primary.Bounds.X -ne 0 -or $primary.Bounds.Y -ne 0 -or
        $primary.Bounds.Width -lt 2000 -or $primary.Bounds.Height -lt 800) {
        throw 'Shared layout requires an origin primary monitor at least 2000x800; WeCom needs 986 pixels per window.'
    }
} elseif ($screens.Count -ne 2 -or $screens[0].Bounds.X -ne 0 -or $screens[1].Bounds.X -ne 1280 -or
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

function Select-AppPlacementWindows {
    param([string]$AppName, [object[]]$Windows)
    # Once logged in, menus, settings and verification dialogs belong to
    # WeCom. They are not additional login windows to center or maximize.
    if ($AppName -eq 'WeCom') {
        $main = @($Windows | Where-Object { $_.ClassName -eq 'WeWorkWindow' })
        if ($main.Count -gt 0) { return $main }
    }
    if ($AppName -eq 'WeChat') {
        # Search results and Channels menus are separate top-level Qt windows.
        # Moving them as "login" windows invalidates native click coordinates.
        # A logged-in main window can use the account name rather than Weixin.
        $main = @($Windows | Where-Object {
            $_.ClassName -eq 'Qt51514QWindowIcon' -and $_.Width -ge 700 -and
            $_.Height -ge 500 -and [AppScreens]::IsMainWindow($_.Handle)
        })
        if ($main.Count -eq 1) { return $main }
        if ($main.Count -gt 1) { return @() }
        return @($Windows | Where-Object {
            $_.Name -in @('Weixin', 'WeChat', '微信') -and
            $_.ClassName -eq 'Qt51514QWindowIcon' -and $_.Width -lt 700 -and
            $_.Height -gt $_.Width
        })
    }
    return $Windows
}

$apps = @(@{ Name = 'WeChat'; Processes = @('WeChat', 'Weixin'); Side = 1 })
if ($Layout -eq 'Shared') {
    $apps = @(@{ Name = 'WeCom'; Processes = @('WXWork'); Side = 0 }) + $apps
}
do {
    # Windows can change resolution while this long-lived guard remains alive.
    $screens = @([System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.Left })
    $primary = [System.Windows.Forms.Screen]::PrimaryScreen
    $area = if ($Layout -eq 'Shared') { [AppScreens]::PrimaryWorkingArea() } else { $null }
    $layoutReady = if ($Layout -eq 'Shared') {
        $area.X -eq 0 -and $area.Y -eq 0 -and $area.Width -ge 2000 -and $area.Height -ge 800
    } else {
        $screens.Count -eq 2 -and $screens[1].Bounds.X -eq 1280
    }
    $changed = $false
    $placed = @()
    $live = @{}
    foreach ($app in $apps) {
        if (-not $layoutReady) { continue }
        $ids = @(Get-Process -Name $app.Processes -ErrorAction SilentlyContinue | ForEach-Object Id)
        $windows = @(Select-AppPlacementWindows -AppName $app.Name -Windows (
            [LabCanvasDesktop.NativeWindows]::Snapshot([int[]]$ids)
        ))
        foreach ($window in $windows) {
            $rect = $window
            if ($rect.Width -lt 200 -or $rect.Height -lt 200 -or
                $window.ClassName -in @('PerryShadowWnd', 'TitleBarWindow')) { continue }
            $handle = $window.Handle
            $kind = if ($rect.Width -lt 700) { 'login' } else { 'main' }
            $key = '{0}-{1}-{2}' -f $window.ProcessId,$handle,$kind
            $live[$key] = $true
            if ($Layout -eq 'Shared') {
                $half = [int][Math]::Floor($area.Width / 2)
                $b = New-Object System.Drawing.Rectangle(
                    ($area.X + [int]$app.Side * ($half + 4)), $area.Y,
                    ($half - 4), $area.Height
                )
            } else { $b = $screens[1].WorkingArea }
            $areaKey = '{0},{1},{2},{3}' -f $b.X,$b.Y,$b.Width,$b.Height
            if ($seen.ContainsKey($key) -and $seen[$key] -eq $areaKey) { continue }
            if ($b.Width -lt 700 -or $b.Height -lt 600) { continue }
            if ($kind -eq 'login') {
                $w = [int]$rect.Width; $h = [int]$rect.Height
                $x = $b.X + [int](($b.Width-$w)/2); $y = $b.Y + [int](($b.Height-$h)/2)
            } else { $x=$b.X; $y=$b.Y; $w=$b.Width; $h=$b.Height }
            # Restore only when placing a new window, never on every watch tick.
            if ($Layout -eq 'Shared') { [AppScreens]::ShowWindow($handle,9) | Out-Null }
            [AppScreens]::SetWindowPos($handle,[IntPtr]::Zero,$x,$y,$w,$h,0x0014) | Out-Null
            $seen[$key] = $areaKey
            $placed += "$($app.Name)-$kind"
            $changed = $true
        }
    }
    # Keep only currently visible window identities, not years of handle history.
    foreach ($key in @($seen.Keys)) {
        if (-not $live.ContainsKey($key)) { $seen.Remove($key) }
    }
    $screenState = if ($Layout -eq 'Shared') {
        @(@{ name='primary'; x=0; y=0; width=[AppScreens]::GetSystemMetrics(0); height=[AppScreens]::GetSystemMetrics(1); primary=$true })
    } else {
        @($screens | ForEach-Object { @{ name=$_.DeviceName; x=$_.Bounds.X; y=$_.Bounds.Y; width=$_.Bounds.Width; height=$_.Bounds.Height; primary=$_.Primary } })
    }
    $result = [ordered]@{ observed_at = [DateTimeOffset]::Now.ToString('o'); placed = $placed; layout = $Layout
        layout_ready = $layoutReady; screens = $screenState }
    if ($first -or $changed) {
        $result | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 C:\LabCanvas\Displays\screens.json
        $first = $false
    }
    if ($Watch) { Start-Sleep -Seconds 3 }
} while ($Watch)
