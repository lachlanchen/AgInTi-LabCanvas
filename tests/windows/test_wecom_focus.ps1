param([string]$Source = 'C:\LabCanvas\WeComBridge\WeComBridge.ps1')
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Bridge source did not parse.' }
$focus = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Focus-WeCom'
}, $false)
if (-not $focus) { throw 'Focus-WeCom not found.' }

# Exercise the deployed function without importing the listener or calling any
# Windows input API. This can run in SSH session zero without touching apps.
Add-Type @'
using System;
public static class LabCanvasWin32 {
    public static IntPtr Foreground, Owner;
    public static int Calls;
    public static bool CanFocus;
    public static IntPtr GetForegroundWindow() { return Foreground; }
    public static IntPtr GetAncestor(IntPtr h, uint flags) { return Owner; }
    public static bool SetForegroundWindow(IntPtr h) {
        Calls++; if (CanFocus) Foreground=h; return CanFocus;
    }
}
'@
function Get-WeComWindow { return [pscustomobject]@{Handle=[IntPtr]77} }
Invoke-Expression $focus.Extent.Text
$cases = @(
    @{Name='already focused'; Foreground=77; Owner=77; CanFocus=$true; Calls=0; Throws=$false},
    @{Name='owned dialog'; Foreground=88; Owner=77; CanFocus=$true; Calls=0; Throws=$false},
    @{Name='another app'; Foreground=99; Owner=99; CanFocus=$true; Calls=1; Throws=$false},
    @{Name='focus denied'; Foreground=99; Owner=99; CanFocus=$false; Calls=1; Throws=$true}
)
foreach ($case in $cases) {
    [LabCanvasWin32]::Foreground=[IntPtr]$case.Foreground
    [LabCanvasWin32]::Owner=[IntPtr]$case.Owner
    [LabCanvasWin32]::CanFocus=$case.CanFocus
    [LabCanvasWin32]::Calls=0
    $threw=$false
    try { Focus-WeCom | Out-Null } catch {
        $threw=$true
        if ($_.Exception.Message -notlike '*refusing input into another app*') { throw }
    }
    if ($threw -ne $case.Throws -or [LabCanvasWin32]::Calls -ne $case.Calls) {
        throw "Failed focus guard case: $($case.Name)"
    }
}
Write-Output 'PASS: four focus cases; no live GUI input'
