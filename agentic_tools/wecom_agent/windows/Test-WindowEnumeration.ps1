param(
    [ValidateSet('Native','UIAutomation')][string]$Method = 'Native',
    [ValidateRange(100,10000)][int]$Iterations = 2000,
    [string]$OutputPath = 'C:\LabCanvas\Displays\window-memory-test.json'
)
$ErrorActionPreference = 'Stop'
if ([System.Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
    throw 'Run in the interactive desktop through a temporary scheduled task.'
}
. "$PSScriptRoot\NativeWindows.ps1"
if ($Method -eq 'UIAutomation') {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
}
$ids = [int[]]@(Get-Process WXWork,Weixin,WeChat -ErrorAction SilentlyContinue | ForEach-Object Id)
if (-not $ids.Count) { throw 'No target application to test.' }
$samples = @()
for ($i=0; $i -le $Iterations; $i++) {
    if ($i % 100 -eq 0) {
        [GC]::Collect(); [GC]::WaitForPendingFinalizers(); [GC]::Collect()
        $process = [System.Diagnostics.Process]::GetCurrentProcess()
        $samples += [pscustomobject]@{ iteration=$i; private_bytes=$process.PrivateMemorySize64; handles=$process.HandleCount }
        $process.Dispose()
        if ($samples[-1].private_bytes -gt 512MB) { break }
    }
    if ($i -eq $Iterations) { break }
    if ($Method -eq 'Native') {
        $windows = [LabCanvasDesktop.NativeWindows]::Snapshot($ids)
        $count = $windows.Count
    } else {
        $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
            [System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
        $count = 0
        foreach ($window in $windows) {
            if ($ids -contains $window.Current.ProcessId) {
                $rect = $window.Current.BoundingRectangle
                if ($rect.Width -ge 200 -and $rect.Height -ge 200) { $count++ }
            }
        }
        $window = $null
    }
    $windows = $null
}
$growth = $samples[-1].private_bytes - $samples[0].private_bytes
$result = [ordered]@{
    method=$Method; iterations=$Iterations; target_windows=$count
    private_growth_bytes=$growth; samples=$samples
    passed=($i -eq $Iterations -and $count -gt 0 -and $growth -lt 64MB -and $samples[-1].private_bytes -lt 512MB)
}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
if (-not $result.passed) { exit 1 }
