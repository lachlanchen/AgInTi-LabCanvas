param(
    [int]$Port = 19582,
    [string]$TokenPath = "C:\LabCanvas\WeComBridge\token.txt",
    [string]$LogPath = "C:\LabCanvas\WeComBridge\bridge.log"
)

$ErrorActionPreference = "Stop"
$script:TargetApp = 'wecom'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
. "$PSScriptRoot\NativeWindows.ps1"

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class LabCanvasWin32 {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern IntPtr GetAncestor(IntPtr hWnd, uint flags);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint flags, uint dx, uint dy, int data, UIntPtr extraInfo);
}
"@

$BridgeRoot = Split-Path -Parent $TokenPath
New-Item -ItemType Directory -Force -Path $BridgeRoot | Out-Null
$Token = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($Token)) {
    throw "The bridge token is empty."
}

function Write-BridgeLog {
    param([string]$Message)
    $line = "{0} {1}" -f ([DateTimeOffset]::Now.ToString("o")), $Message
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value $line
    if ((Test-Path -LiteralPath $LogPath) -and (Get-Item -LiteralPath $LogPath).Length -gt 1048576) {
        $tail = Get-Content -LiteralPath $LogPath -Tail 400
        Set-Content -LiteralPath $LogPath -Encoding UTF8 -Value $tail
    }
}

function Get-WeComWindow {
    # The legacy function name is retained; every request selects one app only.
    $names = if ($script:TargetApp -eq 'wechat') { @('Weixin', 'WeChat') } else { @('WXWork') }
    $processIds = @(Get-Process -Name $names -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    if ($processIds.Count -eq 0) {
        return $null
    }
    return [LabCanvasDesktop.NativeWindows]::Snapshot([int[]]$processIds) |
        Where-Object { $_.Width -ge 700 -and $_.Height -ge 500 -and
            $_.ClassName -notin @('PerryShadowWnd', 'TitleBarWindow') } |
        Sort-Object { $_.Width * $_.Height } -Descending | Select-Object -First 1
}

function Focus-WeCom {
    $window = Get-WeComWindow
    if ($null -eq $window) {
        throw "No visible WeCom window was found in the interactive session."
    }
    # Preserve the current size. Exact-chat OCR and the following click must
    # use the same frame; resizing between those two steps invalidates the
    # calculated coordinates.
    $foreground = [LabCanvasWin32]::GetForegroundWindow()
    [uint32]$foregroundProcessId = 0
    [LabCanvasWin32]::GetWindowThreadProcessId($foreground, [ref]$foregroundProcessId) | Out-Null
    # GA_ROOTOWNER keeps WeCom's file picker or owned dialog active. Neither
    # polling nor an already-focused input sequence needs another focus event.
    if ($foreground -ne $window.Handle -and
        $foregroundProcessId -ne $window.ProcessId -and
        [LabCanvasWin32]::GetAncestor($foreground, 3) -ne $window.Handle) {
        [LabCanvasWin32]::SetForegroundWindow($window.Handle) | Out-Null
        Start-Sleep -Milliseconds 80
        if ([LabCanvasWin32]::GetForegroundWindow() -ne $window.Handle) {
            throw 'WeCom could not receive focus; refusing input into another app.'
        }
    }
    return $window
}

function Invoke-Key {
    param([string]$Keys)
    $mapping = @{
        "ctrl+a" = "^a"
        "ctrl+c" = "^c"
        "ctrl+v" = "^v"
        "alt+s" = "%s"
        "return" = "{ENTER}"
        "enter" = "{ENTER}"
        "home" = "{HOME}"
        "end" = "{END}"
        "up" = "{UP}"
        "down" = "{DOWN}"
        "pagedown" = "{PGDN}"
        "pageup" = "{PGUP}"
        "backspace" = "{BACKSPACE}"
        "escape" = "{ESC}"
    }
    $normalized = $Keys.Trim().ToLowerInvariant()
    if (-not $mapping.ContainsKey($normalized)) {
        throw "Unsupported key chord: $Keys"
    }
    Focus-WeCom | Out-Null
    [System.Windows.Forms.SendKeys]::SendWait($mapping[$normalized])
    Start-Sleep -Milliseconds 60
}

function Invoke-ClipboardOperation {
    param([scriptblock]$Operation)
    # Only clipboard access is retried, never a click or message submission.
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        try { return (& $Operation) } catch {
            if ($attempt -eq 9) { throw }
            Start-Sleep -Milliseconds 100
        }
    }
}

function Invoke-BridgeAction {
    param($Action)
    $kind = [string]$Action.action
    switch ($kind) {
        { $_ -in @('restore', 'activate') } {
            if ($script:TargetApp -ne 'wechat') { throw 'Restore is scoped to personal WeChat.' }
            if ($kind -eq 'restore' -and $null -ne (Get-WeComWindow)) { return $true }
            $ids = @(Get-Process -Name @('Weixin','WeChat') -ErrorAction SilentlyContinue | ForEach-Object Id)
            $candidates = @([LabCanvasDesktop.NativeWindows]::Snapshot([int[]]$ids, $true) |
                Where-Object { $_.Name -in @('Weixin','WeChat','微信') -and
                    $_.ClassName -eq 'Qt51514QWindowIcon' -and $_.Width -ge 700 -and $_.Height -ge 500 })
            if ($candidates.Count -ne 1) { throw 'No unique existing WeChat main window to restore.' }
            # Ask the running client to restore through its normal hotkey.
            # ShowWindow leaves a tray-hidden Qt surface white; starting the
            # executable can open another account login instead of restoring it.
            [System.Windows.Forms.SendKeys]::SendWait('^%w')
            Start-Sleep -Milliseconds 1000
            return $true
        }
        "click" {
            $window = Focus-WeCom
            Assert-AppPoint $window $Action
            [LabCanvasWin32]::SetCursorPos([int]$Action.x, [int]$Action.y) | Out-Null
            [LabCanvasWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
            [LabCanvasWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
        }
        "right_click" {
            $window = Focus-WeCom
            Assert-AppPoint $window $Action
            [LabCanvasWin32]::SetCursorPos([int]$Action.x, [int]$Action.y) | Out-Null
            [LabCanvasWin32]::mouse_event(0x0008, 0, 0, 0, [UIntPtr]::Zero)
            [LabCanvasWin32]::mouse_event(0x0010, 0, 0, 0, [UIntPtr]::Zero)
        }
        "wheel" {
            $window = Focus-WeCom
            if ($null -ne $Action.x -and $null -ne $Action.y) {
                Assert-AppPoint $window $Action
                [LabCanvasWin32]::SetCursorPos([int]$Action.x, [int]$Action.y) | Out-Null
            }
            [LabCanvasWin32]::mouse_event(0x0800, 0, 0, [int]$Action.delta, [UIntPtr]::Zero)
        }
        "key" {
            Invoke-Key -Keys ([string]$Action.keys)
        }
        "set_clipboard" {
            if ([string]::IsNullOrEmpty([string]$Action.text)) {
                Invoke-ClipboardOperation { [System.Windows.Forms.Clipboard]::Clear() }
            } else {
                Invoke-ClipboardOperation { [System.Windows.Forms.Clipboard]::SetText([string]$Action.text) }
            }
        }
        "get_clipboard" {
            return Invoke-ClipboardOperation { [System.Windows.Forms.Clipboard]::GetText() }
        }
        "set_file_clipboard" {
            $files = New-Object System.Collections.Specialized.StringCollection
            foreach ($path in @($Action.paths)) {
                $resolved = [System.IO.Path]::GetFullPath([string]$path)
                if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
                    throw "Clipboard file does not exist: $resolved"
                }
                [void]$files.Add($resolved)
            }
            Invoke-ClipboardOperation { [System.Windows.Forms.Clipboard]::SetFileDropList($files) }
            return @($files)
        }
        "macro" {
            $results = @()
            foreach ($item in @($Action.actions)) {
                $results += ,(Invoke-BridgeAction -Action $item)
            }
            return $results
        }
        default {
            throw "Unsupported bridge action: $kind"
        }
    }
    Start-Sleep -Milliseconds 70
    return $true
}

function Assert-AppPoint {
    param($Window, $Action)
    # On a shared console, focusing one app does not constrain pointer input.
    # Reject stale coordinates rather than clicking the neighbouring account.
    if ($null -eq $Action.x -or $null -eq $Action.y -or
        $Action.x -lt $Window.X -or $Action.x -ge ($Window.X + $Window.Width) -or
        $Action.y -lt $Window.Y -or $Action.y -ge ($Window.Y + $Window.Height)) {
        throw 'Input point is outside the selected app; refusing cross-app input.'
    }
}

function Write-JsonResponse {
    param($Response, $Payload, [int]$StatusCode = 200)
    $body = [System.Text.Encoding]::UTF8.GetBytes(($Payload | ConvertTo-Json -Depth 10 -Compress))
    $Response.StatusCode = $StatusCode
    $Response.ContentType = "application/json; charset=utf-8"
    $Response.ContentLength64 = $body.Length
    $Response.OutputStream.Write($body, 0, $body.Length)
    $Response.Close()
}

function Write-ScreenshotResponse {
    param($Response)
    # Preserve desktop coordinates while capturing only WeCom, including when
    # both apps share one monitor. The owner's noVNC view remains unmasked.
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $window = Get-WeComWindow
    if ($bounds.X -ne 0 -or $bounds.Y -ne 0 -or ($null -ne $window -and
        -not $bounds.Contains([int]($window.X + $window.Width/2), [int]($window.Y + $window.Height/2)))) {
        throw 'WeCom is outside its origin monitor; refusing cross-app capture.'
    }
    if ($null -eq $window) { throw 'No visible WeCom window; refusing desktop capture.' }
    $rect = New-Object System.Drawing.Rectangle($window.X,$window.Y,$window.Width,$window.Height)
    $region = [System.Drawing.Rectangle]::Intersect($bounds,$rect)
    $otherNames = if ($script:TargetApp -eq 'wechat') { @('WXWork') } else { @('WeChat', 'Weixin') }
    $wechatIds = @(Get-Process -Name $otherNames -ErrorAction SilentlyContinue | ForEach-Object Id)
    foreach ($other in [LabCanvasDesktop.NativeWindows]::Snapshot([int[]]$wechatIds)) {
        if ($other.ClassName -in @('PerryShadowWnd', 'TitleBarWindow')) { continue }
        $otherRect = New-Object System.Drawing.Rectangle($other.X,$other.Y,$other.Width,$other.Height)
        if ($region.IntersectsWith($otherRect)) {
            throw 'WeChat overlaps WeCom; refusing cross-app capture.'
        }
    }
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $stream = New-Object System.IO.MemoryStream
    try {
        $graphics.Clear([System.Drawing.Color]::Black)
        $graphics.CopyFromScreen($region.Left, $region.Top,
            ($region.Left-$bounds.Left), ($region.Top-$bounds.Top), $region.Size)
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
        $body = $stream.ToArray()
        $Response.StatusCode = 200
        $Response.ContentType = "image/png"
        $Response.ContentLength64 = $body.Length
        $Response.OutputStream.Write($body, 0, $body.Length)
        $Response.Close()
    }
    finally {
        $stream.Dispose()
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://127.0.0.1:$Port/")
$listener.Start()
Write-BridgeLog "started port=$Port session=$([System.Diagnostics.Process]::GetCurrentProcess().SessionId)"

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            $authorization = [string]$context.Request.Headers["Authorization"]
            if ($authorization -ne "Bearer $Token") {
                Write-JsonResponse $context.Response ([ordered]@{ ok = $false; error = "unauthorized" }) 401
                continue
            }
            $script:TargetApp = [string]$context.Request.Headers['X-LabCanvas-App']
            if ([string]::IsNullOrEmpty($script:TargetApp)) { $script:TargetApp = 'wecom' }
            if ($script:TargetApp -notin @('wecom', 'wechat')) {
                Write-JsonResponse $context.Response @{ ok = $false; error = 'invalid_app' } 400
                continue
            }
            $path = $context.Request.Url.AbsolutePath
            if ($context.Request.HttpMethod -eq "GET" -and $path -eq "/health") {
                $window = Get-WeComWindow
                $payload = [ordered]@{
                    ok = ($null -ne $window)
                    app = $script:TargetApp
                    session_id = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
                    wecom_running = (@(Get-Process WXWork -ErrorAction SilentlyContinue).Count -gt 0)
                    window = if ($null -eq $window) { $null } else {
                        [ordered]@{
                            name = $window.Name
                            class_name = $window.ClassName
                            process_id = $window.ProcessId
                            handle = $window.Handle.ToInt64()
                            x = $window.X
                            y = $window.Y
                            width = $window.Width
                            height = $window.Height
                        }
                    }
                }
                Write-JsonResponse $context.Response $payload
                continue
            }
            if ($context.Request.HttpMethod -eq "GET" -and $path -eq "/screenshot") {
                Write-ScreenshotResponse $context.Response
                continue
            }
            if ($context.Request.HttpMethod -eq "POST" -and $path -eq "/action") {
                $reader = New-Object System.IO.StreamReader($context.Request.InputStream, [System.Text.Encoding]::UTF8)
                try {
                    $raw = $reader.ReadToEnd()
                }
                finally {
                    $reader.Dispose()
                }
                if ([System.Text.Encoding]::UTF8.GetByteCount($raw) -gt 2097152) {
                    throw "Action body exceeds 2 MiB."
                }
                $action = $raw | ConvertFrom-Json
                $result = Invoke-BridgeAction -Action $action
                Write-JsonResponse $context.Response ([ordered]@{ ok = $true; result = $result })
                continue
            }
            Write-JsonResponse $context.Response ([ordered]@{ ok = $false; error = "not_found" }) 404
        }
        catch {
            Write-BridgeLog ("request_error " + $_.Exception.Message)
            if ($null -ne $context.Response -and $context.Response.OutputStream.CanWrite) {
                Write-JsonResponse $context.Response ([ordered]@{ ok = $false; error = $_.Exception.Message }) 500
            }
        }
    }
}
finally {
    $listener.Stop()
    $listener.Close()
    Write-BridgeLog "stopped"
}
