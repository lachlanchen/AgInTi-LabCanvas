param(
    [Parameter(Mandatory=$true)][string]$ExpectedComputer,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9-]{0,14}$')][string]$NewName = 'LABCANVAS-PC',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$current = $env:COMPUTERNAME
if ($current -ne $ExpectedComputer) { throw 'Unexpected computer; refusing rename.' }
if ((Get-CimInstance Win32_ComputerSystem).PartOfDomain) { throw 'Local dedicated workstation only.' }
$winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$oldDomain = (Get-ItemProperty $winlogon -Name DefaultDomainName -ErrorAction SilentlyContinue).DefaultDomainName
$tasks = @(Get-ScheduledTask -TaskName 'LabCanvas*' -ErrorAction SilentlyContinue)
if (-not $Apply) {
    [ordered]@{ current=$current; requested=$NewName; apply=$false; reboot_required=($current -ne $NewName)
        local_autologon_domain=($oldDomain -eq $current); tasks=@($tasks.TaskName) } | ConvertTo-Json -Compress
    exit
}
$backup = 'C:\LabCanvas\Recovery\rename-' + (Get-Date -Format 'yyyyMMddTHHmmss')
New-Item -ItemType Directory -Path $backup -Force | Out-Null
# Task principals use SIDs so a local computer rename cannot orphan them.
foreach ($task in $tasks) {
    $xml = Export-ScheduledTask -TaskName $task.TaskName
    $xml | Set-Content -LiteralPath "$backup\$($task.TaskName).xml" -Encoding UTF8
    [xml]$document = $xml
    $changed = $false
    foreach ($node in $document.SelectNodes("//*[local-name()='UserId']")) {
        if ($node.InnerText -notmatch '^S-1-') {
            $account = New-Object System.Security.Principal.NTAccount($node.InnerText)
            $node.InnerText = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
            $changed = $true
        }
    }
    if ($changed) { Register-ScheduledTask -TaskName $task.TaskName -Xml $document.OuterXml -Force | Out-Null }
}
if ($current -ne $NewName) { Rename-Computer -NewName $NewName -Force }
# Preserve the LSA password, user profile, app databases, and SSH identity.
if ($oldDomain -eq $current) { Set-ItemProperty $winlogon -Name DefaultDomainName -Value $NewName }
[ordered]@{ previous=$current; requested=$NewName; apply=$true; reboot_required=($current -ne $NewName)
    backup=$backup; password_changed=$false; profiles_changed=$false } | ConvertTo-Json -Compress
