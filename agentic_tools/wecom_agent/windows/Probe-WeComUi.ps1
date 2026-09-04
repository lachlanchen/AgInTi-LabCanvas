param(
    [string]$OutputPath = "C:\LabCanvas\WeComBridge\probe.json",
    [int]$MaxElements = 800
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$processes = @(Get-Process WXWork -ErrorAction SilentlyContinue)
$processIds = @($processes | ForEach-Object { $_.Id })
$condition = [System.Windows.Automation.Condition]::TrueCondition
$root = [System.Windows.Automation.AutomationElement]::RootElement
$windows = @()

foreach ($window in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)) {
    if ($processIds -notcontains $window.Current.ProcessId) {
        continue
    }

    $elements = @()
    foreach ($element in $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)) {
        if ($elements.Count -ge $MaxElements) {
            break
        }
        $name = [string]$element.Current.Name
        $automationId = [string]$element.Current.AutomationId
        if ([string]::IsNullOrWhiteSpace($name) -and [string]::IsNullOrWhiteSpace($automationId)) {
            continue
        }
        $rectangle = $element.Current.BoundingRectangle
        $elements += [ordered]@{
            name = $name
            automation_id = $automationId
            control_type = [string]$element.Current.ControlType.ProgrammaticName
            class_name = [string]$element.Current.ClassName
            enabled = [bool]$element.Current.IsEnabled
            offscreen = [bool]$element.Current.IsOffscreen
            x = [math]::Round($rectangle.X, 1)
            y = [math]::Round($rectangle.Y, 1)
            width = [math]::Round($rectangle.Width, 1)
            height = [math]::Round($rectangle.Height, 1)
        }
    }

    $windowRectangle = $window.Current.BoundingRectangle
    $windows += [ordered]@{
        name = [string]$window.Current.Name
        automation_id = [string]$window.Current.AutomationId
        class_name = [string]$window.Current.ClassName
        process_id = [int]$window.Current.ProcessId
        x = [math]::Round($windowRectangle.X, 1)
        y = [math]::Round($windowRectangle.Y, 1)
        width = [math]::Round($windowRectangle.Width, 1)
        height = [math]::Round($windowRectangle.Height, 1)
        elements = $elements
    }
}

$payload = [ordered]@{
    ok = $true
    observed_at = [DateTimeOffset]::Now.ToString("o")
    session_id = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
    wxwork_process_ids = $processIds
    windows = $windows
}

$payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $OutputPath
