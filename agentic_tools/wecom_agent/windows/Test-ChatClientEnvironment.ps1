param(
    [ValidateSet('Status', 'RepairTime', 'RestoreTime')][string]$Mode = 'Status',
    [string]$ExpectedComputer = 'LABCANVAS-PC',
    [string]$BackupPath = 'C:\LabCanvas\EnvironmentHealth\time-before.json'
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) { throw 'Unexpected computer.' }

if (-not ('LabCanvasEnvironment.Console' -as [type])) {
    Add-Type @'
using System.Runtime.InteropServices;
namespace LabCanvasEnvironment {
    public static class Console {
        [DllImport("kernel32.dll")]
        public static extern uint WTSGetActiveConsoleSessionId();
    }
}
'@
}

function Read-TimeService {
    $service = Get-CimInstance Win32_Service -Filter "Name='W32Time'"
    [ordered]@{ state = $service.State; start_mode = $service.StartMode }
}

function Read-Clients {
    foreach ($name in @('Weixin.exe', 'WXWork.exe')) {
        $processes = @(Get-CimInstance Win32_Process -Filter "Name='$name'")
        $roots = @($processes | Where-Object { $_.ParentProcessId -notin $processes.ProcessId })
        $signatures = @(foreach ($path in @($processes.ExecutablePath | Sort-Object -Unique)) {
            if (-not $path) { continue }
            $signature = Get-AuthenticodeSignature -LiteralPath $path
            $file = Get-Item -LiteralPath $path
            [ordered]@{
                status = $signature.Status.ToString()
                publisher = $signature.SignerCertificate.Subject
                version = $file.VersionInfo.ProductVersion
            }
        })
        [ordered]@{
            name = $name; root_instances = $roots.Count
            roots = @($roots | Select-Object ProcessId, SessionId, CreationDate)
            session_ids = @($processes.SessionId | Sort-Object -Unique)
            signatures = $signatures
        }
    }
}

$clientsBefore = @(Read-Clients)
$before = Read-TimeService
$resyncExitCode = $null
if ($Mode -ne 'Status') {
    $principal = New-Object Security.Principal.WindowsPrincipal(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Time repair requires an administrative SSH session; no GUI elevation will be attempted.'
    }
}
if ($Mode -eq 'RepairTime') {
    if (-not (Test-Path -LiteralPath $BackupPath)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $BackupPath) | Out-Null
        [ordered]@{ computer = $env:COMPUTERNAME; observed_at = [DateTimeOffset]::Now.ToString('o'); service = $before } |
            ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $BackupPath -Encoding utf8
    }
    # Keep the existing NTP/domain configuration, timezone, and client profiles.
    Set-Service -Name W32Time -StartupType Automatic
    Start-Service -Name W32Time
    & w32tm.exe /resync 2>&1 | Out-Null
    $resyncExitCode = $LASTEXITCODE
} elseif ($Mode -eq 'RestoreTime') {
    $saved = Get-Content -LiteralPath $BackupPath | ConvertFrom-Json
    if ($saved.computer -ne $env:COMPUTERNAME) { throw 'Backup computer mismatch.' }
    $startup = switch ($saved.service.start_mode) {
        'Auto' { 'Automatic' }; 'Manual' { 'Manual' }; 'Disabled' { 'Disabled' }
        default { throw 'Invalid saved startup type.' }
    }
    if ($saved.service.state -notin @('Running', 'Stopped')) { throw 'Invalid saved service state.' }
    if ($saved.service.state -eq 'Stopped') { Stop-Service -Name W32Time }
    Set-Service -Name W32Time -StartupType $startup
    if ($saved.service.state -eq 'Running') { Start-Service -Name W32Time }
}

$issues = New-Object 'System.Collections.Generic.List[string]'
$console = [LabCanvasEnvironment.Console]::WTSGetActiveConsoleSessionId()
$clientsAfter = @(Read-Clients)
$defender = $null
try {
    $status = Get-MpComputerStatus
    $defender = [ordered]@{
        antivirus_enabled = $status.AntivirusEnabled
        realtime_enabled = $status.RealTimeProtectionEnabled
        signatures_outdated = $status.DefenderSignaturesOutOfDate
    }
    if (-not $status.AntivirusEnabled -or -not $status.RealTimeProtectionEnabled) { $issues.Add('defender_protection_disabled') }
    if ($status.DefenderSignaturesOutOfDate) { $issues.Add('defender_signatures_outdated') }
} catch { $issues.Add('defender_status_unavailable') }
$uac = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System').EnableLUA
if ($uac -ne 1) { $issues.Add('uac_disabled') }
$after = Read-TimeService
if ($after.state -ne 'Running') { $issues.Add('time_service_not_running') }
if ($null -ne $resyncExitCode -and $resyncExitCode -ne 0) { $issues.Add('time_resync_failed') }
if ($console -eq [uint32]::MaxValue) { $issues.Add('no_console_session') }
foreach ($client in $clientsAfter) {
    if ($client.root_instances -gt 1) { $issues.Add("multiple_client_roots:$($client.name)") }
    if (@($client.session_ids | Where-Object { $_ -ne $console }).Count) { $issues.Add("non_console_client:$($client.name)") }
    if ($client.root_instances -and -not $client.signatures.Count) { $issues.Add("signature_unavailable:$($client.name)") }
    foreach ($signature in $client.signatures) {
        if ($signature.status -ne 'Valid' -or $signature.publisher -notmatch 'Tencent') {
            $issues.Add("unverified_client_binary:$($client.name)")
        }
    }
}
$beforeIdentity = $clientsBefore | ConvertTo-Json -Depth 6 -Compress
$afterIdentity = $clientsAfter | ConvertTo-Json -Depth 6 -Compress
$clientsUnchanged = ($beforeIdentity -ceq $afterIdentity)
if (-not $clientsUnchanged) { $issues.Add('client_processes_changed_during_audit') }
[ordered]@{
    ok = ($issues.Count -eq 0); mode = $Mode; issues = @($issues.ToArray())
    observed_at = [DateTimeOffset]::Now.ToString('o'); computer = $env:COMPUTERNAME
    console_session_id = $console; uac_enabled = ($uac -eq 1); defender = $defender
    clients = $clientsAfter; client_processes_unchanged = $clientsUnchanged
    time_before = $before; time_after = $after; time_resync_exit_code = $resyncExitCode
    time_backup = $(if ($Mode -ne 'Status') { $BackupPath } else { $null })
    applications_restarted = $false; reboot_performed = $false
    security_prompts_suppressed = $false
} | ConvertTo-Json -Depth 8 -Compress
