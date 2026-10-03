param(
    [switch]$Apply,
    [switch]$StartMissing,
    [string]$ExpectedComputer = 'LABCANVAS-PC'
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) { throw 'Unexpected computer.' }
if ($StartMissing -and -not $Apply) { throw 'Starting a missing client requires Apply.' }

$name = 'LabCanvas-Start-Weixin-Once'
$task = Get-ScheduledTask -TaskName $name
$allowed = @(
    'C:\Program Files\Tencent\Weixin\Weixin.exe',
    'C:\Program Files\Tencent\WeChat\WeChat.exe',
    'C:\Program Files (x86)\Tencent\WeChat\WeChat.exe'
)
if ($task.Actions.Count -ne 1 -or $task.Actions[0].Execute -notin $allowed -or
    $task.Actions[0].Arguments -or [int]$task.Principal.LogonType -ne 3) {
    throw 'Unexpected client task action or principal; refusing changes.'
}
$exe = $task.Actions[0].Execute
if (-not (Test-Path -LiteralPath $exe)) { throw 'Installed client is missing.' }
$signature = Get-AuthenticodeSignature -LiteralPath $exe
if ($signature.Status -ne 'Valid' -or
    $signature.SignerCertificate.Subject -notmatch '^CN=Tencent Technology \(Shenzhen\) Company Limited,') {
    throw 'Installed client does not have a valid Tencent signature.'
}
$before = $task.Settings.ExecutionTimeLimit
$changed = $false
if ($Apply -and $before -ne 'PT0S') {
    $backup = 'C:\LabCanvas\Recovery\wechat-launch-task'
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    $path = Join-Path $backup ('before-{0}.xml' -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ'))
    Export-ScheduledTask -TaskName $name | Set-Content -LiteralPath $path -Encoding UTF8
    # Retain principal, triggers, action, and every other existing setting.
    $task.Settings.ExecutionTimeLimit = 'PT0S'
    Set-ScheduledTask -TaskName $name -Settings $task.Settings | Out-Null
    $changed = $true
}
$clients = @(Get-Process Weixin,WeChat -ErrorAction SilentlyContinue)
$started = $false
if ($StartMissing -and $clients.Count -eq 0) {
    Start-ScheduledTask -TaskName $name
    $started = $true
}
[ordered]@{
    ok = $true
    task_name = $name
    applied = [bool]$Apply
    changed = $changed
    started = $started
    existing_client_count = $clients.Count
    execution_time_limit_before = $before
    execution_time_limit = (Get-ScheduledTask -TaskName $name).Settings.ExecutionTimeLimit
    client_login_verified = $false
    wecom_untouched = $true
} | ConvertTo-Json -Compress
