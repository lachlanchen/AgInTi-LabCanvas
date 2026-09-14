param([string]$HelperPath = "$PSScriptRoot\WeComBridge.ps1")

# Evaluate only the pure guard, never start a listener or touch a client.
$ErrorActionPreference = 'Stop'
$errors = $null
$tokens = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile($HelperPath, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$guard = $tree.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Get-SystemInputBlocker'
}, $true)
if (-not $guard) { throw 'Missing system-input guard' }
Invoke-Expression $guard.Extent.Text
$cases = @(
    @{ name='PickerHost'; path="$env:WINDIR\System32\PickerHost.exe"; blocked=$true },
    @{ name='consent'; path="$env:WINDIR\System32\consent.exe"; blocked=$true },
    @{ name='LogonUI'; path="$env:WINDIR\System32\LogonUI.exe"; blocked=$true },
    @{ name='CredentialUIBroker'; path="$env:WINDIR\System32\CredentialUIBroker.exe"; blocked=$true },
    @{ name='WXWork'; path='C:\Program Files\Tencent\WXWork.exe'; blocked=$false },
    @{ name='PickerHost'; path='C:\Other\PickerHost.exe'; blocked=$false },
    @{ name='gone'; path=''; blocked=$false }
)
function Get-Process { param($Id) return $script:ProbeProcess }
try {
    if ((Get-SystemInputBlocker 0) -ne 'input_desktop_unavailable') {
        throw 'Unknown foreground must not authorize input'
    }
    foreach ($case in $cases) {
        $script:ProbeProcess = if ($case.name -eq 'gone') { $null } else {
            [pscustomobject]@{ ProcessName=$case.name; Path=$case.path }
        }
        $observed = Get-SystemInputBlocker 123
        if ([bool]$observed -ne $case.blocked) { throw "Guard failed for $($case.name)" }
    }
} finally {
    Remove-Item Function:\Get-Process
}
[ordered]@{ ok=$true; cases=($cases.Count + 1); gui_input_performed=$false } | ConvertTo-Json -Compress
