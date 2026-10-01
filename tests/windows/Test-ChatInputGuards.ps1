param([Parameter(Mandatory=$true)][string]$HelperPath)

$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $HelperPath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw 'Helper PowerShell syntax is invalid.' }

# Load the real guard functions, replacing only OS observations and input APIs.
# This process never opens a window, injects input, or touches a Tencent client.
Add-Type @'
using System;
namespace LabCanvasDesktop {
    public static class NativeWindows {
        public static bool Responding = true, Enabled = true;
        public static bool IsResponding(IntPtr window) { return Responding; }
        public static bool IsWindowEnabled(IntPtr window) { return Enabled; }
    }
}
public static class LabCanvasWin32 {
    public static int FocusCalls = 0;
    public static IntPtr GetForegroundWindow() { return new IntPtr(42); }
    public static uint GetWindowThreadProcessId(IntPtr window, out uint pid) { pid = 42; return 1; }
    public static IntPtr GetAncestor(IntPtr window, uint flags) { return new IntPtr(42); }
    public static bool SetForegroundWindow(IntPtr window) {
        FocusCalls++;
        throw new Exception("Unexpected focus injection in guard test.");
    }
}
'@

foreach ($name in @('Get-AppInputBlocker', 'Focus-WeCom')) {
    $definition = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $true)
    if (-not $definition) { throw "Missing function: $name" }
    . ([scriptblock]::Create($definition.Extent.Text))
}

$script:Window = [pscustomobject]@{Handle=[IntPtr]42;ProcessId=42}
$script:SystemBlocker = ''
function Get-WeComWindow { return $script:Window }
function Get-PersonalWeChatState { return 'ready' }
function Get-SystemInputBlocker { param($ProcessId); return $script:SystemBlocker }
function Test-NativeWebForeground { param($ProcessId, $Window); return $false }

$passed = 0
foreach ($app in @('wechat', 'wecom')) {
    $script:TargetApp = $app
    foreach ($case in @('unresponsive', 'disabled', 'system_dialog', 'ready')) {
        [LabCanvasDesktop.NativeWindows]::Responding = $case -ne 'unresponsive'
        [LabCanvasDesktop.NativeWindows]::Enabled = $case -ne 'disabled'
        $script:SystemBlocker = if ($case -eq 'system_dialog') { 'windows_system_dialog' } else { '' }
        $expected = switch ($case) {
            'unresponsive' { $app.ToUpperInvariant() + '_CLIENT_UNRESPONSIVE:' }
            'disabled' { 'LABCANVAS_GUI_APP_MODAL_BLOCKED:' }
            'system_dialog' { 'LABCANVAS_GUI_SYSTEM_DIALOG_BLOCKED:' }
            'ready' { '' }
        }
        $failure = ''
        try { $result = Focus-WeCom } catch { $failure = $_.Exception.Message }
        if ($expected) {
            if (-not $failure.StartsWith($expected)) { throw "Wrong guard for ${app}/${case}: $failure" }
        } elseif ($failure -or $result.Handle -ne $script:Window.Handle) {
            throw "Healthy ${app} was not accepted: $failure"
        }
        if ([LabCanvasWin32]::FocusCalls -ne 0) { throw 'Guard changed focus.' }
        $passed++
    }
}
[ordered]@{ok=$true;cases=$passed;focus_calls=[LabCanvasWin32]::FocusCalls;synthetic=$true} | ConvertTo-Json -Compress
