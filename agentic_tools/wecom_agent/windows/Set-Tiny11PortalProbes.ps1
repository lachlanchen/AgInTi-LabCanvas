param(
    [ValidateSet('Status', 'Apply', 'Restore')][string]$Mode = 'Status',
    [string]$ExpectedComputer = 'LABCANVAS-PC',
    [string]$BackupPath = 'C:\LabCanvas\BrowserRepair\ncsi-before.json'
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) { throw 'Unexpected computer.' }
$key = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\NetworkConnectivityStatusIndicator'
# Dedicated messaging VM only. Direct endpoint probes replace the Windows
# captive-portal heuristics; applications may otherwise report false offline.
$names = @('NoActiveProbe', 'DisablePassivePolling')
function Read-Values {
    foreach ($name in $names) {
        $item = Get-Item -LiteralPath $key -ErrorAction SilentlyContinue
        $exists = $item -and ($item.GetValueNames() -contains $name)
        [pscustomobject]@{
            name = $name; exists = [bool]$exists
            value = $(if ($exists) { $item.GetValue($name) } else { $null })
            kind = $(if ($exists) { $item.GetValueKind($name).ToString() } else { $null })
        }
    }
}
$before = @(Read-Values)
if ($Mode -eq 'Apply') {
    if (-not (Test-Path -LiteralPath $BackupPath)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $BackupPath) | Out-Null
        @{ computer = $env:COMPUTERNAME; observed_at = [DateTimeOffset]::Now.ToString('o'); values = $before } |
            ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $BackupPath -Encoding utf8
    }
    New-Item -Path $key -Force | Out-Null
    foreach ($name in $names) { New-ItemProperty -Path $key -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
} elseif ($Mode -eq 'Restore') {
    $saved = Get-Content -LiteralPath $BackupPath | ConvertFrom-Json
    if ($saved.computer -ne $env:COMPUTERNAME) { throw 'Backup computer mismatch.' }
    foreach ($entry in $saved.values) {
        if ($entry.name -notin $names) { throw 'Unexpected registry value in backup.' }
        if ($entry.exists) {
            New-ItemProperty -Path $key -Name $entry.name -Value $entry.value -PropertyType $entry.kind -Force | Out-Null
        } else { Remove-ItemProperty -Path $key -Name $entry.name -ErrorAction SilentlyContinue }
    }
}
@{ mode = $Mode; before = $before; after = @(Read-Values); backup = $BackupPath;
   reboot_performed = $false; applications_restarted = $false } | ConvertTo-Json -Depth 5
