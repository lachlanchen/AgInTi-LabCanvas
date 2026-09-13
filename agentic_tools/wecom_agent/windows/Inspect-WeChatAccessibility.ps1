param([string]$OutputPath = 'C:\LabCanvas\WeComBridge\wechat-accessibility.json')

# Run only as a short-lived interactive task. Never retain UIA providers in the relay.
$ErrorActionPreference = 'Stop'
if ([System.Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
    throw 'Use an interactive task, not the SSH service desktop.'
}
. "$PSScriptRoot\NativeWindows.ps1"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ids = @(Get-Process Weixin,WeChat -ErrorAction SilentlyContinue | ForEach-Object Id)
$window = [LabCanvasDesktop.NativeWindows]::Snapshot([int[]]$ids) |
    Where-Object { $_.Width -ge 700 -and $_.Height -ge 500 } |
    Sort-Object { $_.Width * $_.Height } -Descending | Select-Object -First 1
if ($null -eq $window) { throw 'No visible WeChat main window.' }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.Handle)
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$pending = New-Object System.Collections.Queue
$pending.Enqueue(@{ element = $root; parent = -1 })
$records = New-Object System.Collections.Generic.List[object]
$watch = [Diagnostics.Stopwatch]::StartNew()
while ($pending.Count -gt 0 -and $records.Count -lt 1200 -and $watch.Elapsed.TotalSeconds -lt 8) {
    $item = $pending.Dequeue()
    $element = $item.element
    $current = $element.Current
    $rect = $current.BoundingRectangle
    $index = $records.Count
    $records.Add([ordered]@{
        id = $index; parent = $item.parent; name = $current.Name
        automation_id = $current.AutomationId; class_name = $current.ClassName
        control_type = $current.ControlType.ProgrammaticName
        x = $rect.X; y = $rect.Y; width = $rect.Width; height = $rect.Height
        offscreen = $current.IsOffscreen
    })
    $child = $walker.GetFirstChild($element)
    while ($null -ne $child -and $pending.Count -lt 1200) {
        $pending.Enqueue(@{ element = $child; parent = $index })
        $child = $walker.GetNextSibling($child)
    }
}
@{ records = @($records.ToArray()); elapsed_ms = $watch.ElapsedMilliseconds } |
    ConvertTo-Json -Depth 6 -Compress | Set-Content -LiteralPath $OutputPath -Encoding UTF8
