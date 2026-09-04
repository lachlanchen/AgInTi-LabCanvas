param(
    [int]$Port = 19582,
    [string]$TokenPath = "C:\LabCanvas\WeComBridge\token.txt",
    [string]$LogPath = "C:\LabCanvas\WeComBridge\bridge.log"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class LabCanvasWin32 {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

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
    $processIds = @(Get-Process WXWork -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    if ($processIds.Count -eq 0) {
        return $null
    }
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $condition = [System.Windows.Automation.Condition]::TrueCondition
    $candidates = @()
    foreach ($window in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)) {
        if ($processIds -notcontains $window.Current.ProcessId) {
            continue
        }
        $rectangle = $window.Current.BoundingRectangle
        if ($rectangle.Width -lt 700 -or $rectangle.Height -lt 500) {
            continue
        }
        $candidates += [pscustomobject]@{
            Handle = [IntPtr]$window.Current.NativeWindowHandle
            Name = [string]$window.Current.Name
            ClassName = [string]$window.Current.ClassName
            ProcessId = [int]$window.Current.ProcessId
            X = [int][math]::Round($rectangle.X)
            Y = [int][math]::Round($rectangle.Y)
            Width = [int][math]::Round($rectangle.Width)
            Height = [int][math]::Round($rectangle.Height)
        }
    }
    return $candidates | Sort-Object { $_.Width * $_.Height } -Descending | Select-Object -First 1
}

function Focus-WeCom {
    $window = Get-WeComWindow
    if ($null -eq $window) {
        throw "No visible WeCom window was found in the interactive session."
    }
    # Preserve the current size. Exact-chat OCR and the following click must
    # use the same frame; resizing between those two steps invalidates the
    # calculated coordinates.
    [LabCanvasWin32]::ShowWindow($window.Handle, 5) | Out-Null
    [LabCanvasWin32]::SetForegroundWindow($window.Handle) | Out-Null
    Start-Sleep -Milliseconds 80
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

function Invoke-BridgeAction {
    param($Action)
    $kind = [string]$Action.action
    switch ($kind) {
        "click" {
            Focus-WeCom | Out-Null
            [LabCanvasWin32]::SetCursorPos([int]$Action.x, [int]$Action.y) | Out-Null
            [LabCanvasWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
            [LabCanvasWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
        }
        "right_click" {
            Focus-WeCom | Out-Null
            [LabCanvasWin32]::SetCursorPos([int]$Action.x, [int]$Action.y) | Out-Null
            [LabCanvasWin32]::mouse_event(0x0008, 0, 0, 0, [UIntPtr]::Zero)
            [LabCanvasWin32]::mouse_event(0x0010, 0, 0, 0, [UIntPtr]::Zero)
        }
        "wheel" {
            Focus-WeCom | Out-Null
            if ($null -ne $Action.x -and $null -ne $Action.y) {
                [LabCanvasWin32]::SetCursorPos([int]$Action.x, [int]$Action.y) | Out-Null
            }
            [LabCanvasWin32]::mouse_event(0x0800, 0, 0, [int]$Action.delta, [UIntPtr]::Zero)
        }
        "key" {
            Invoke-Key -Keys ([string]$Action.keys)
        }
        "set_clipboard" {
            [System.Windows.Forms.Clipboard]::SetText([string]$Action.text)
        }
        "get_clipboard" {
            return [System.Windows.Forms.Clipboard]::GetText()
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
            [System.Windows.Forms.Clipboard]::SetFileDropList($files)
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
    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $stream = New-Object System.IO.MemoryStream
    try {
        $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)
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
            $path = $context.Request.Url.AbsolutePath
            if ($context.Request.HttpMethod -eq "GET" -and $path -eq "/health") {
                $window = Get-WeComWindow
                $payload = [ordered]@{
                    ok = ($null -ne $window)
                    session_id = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
                    wecom_running = (@(Get-Process WXWork -ErrorAction SilentlyContinue).Count -gt 0)
                    window = if ($null -eq $window) { $null } else {
                        [ordered]@{
                            name = $window.Name
                            class_name = $window.ClassName
                            process_id = $window.ProcessId
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
