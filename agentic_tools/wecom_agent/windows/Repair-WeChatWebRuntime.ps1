param(
    [switch]$Apply,
    [string]$ExpectedComputer = 'LABCANVAS-PC',
    [int]$MinimumRendererCount = 64
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) { throw 'Unexpected computer.' }
if ($MinimumRendererCount -lt 64) { throw 'Refusing a low renderer-count threshold.' }
$processes = @(Get-CimInstance Win32_Process)
$clients = @($processes | Where-Object { $_.Name -in @('Weixin.exe','WeChat.exe','WXWork.exe') })
$personal = @($clients | Where-Object { $_.Name -in @('Weixin.exe','WeChat.exe') })
$roots = @($processes | Where-Object {
    $_.Name -eq 'WeChatAppEx.exe' -and $_.ParentProcessId -in $personal.ProcessId -and
    $_.ExecutablePath -like '*\Tencent\xwechat\xplugin\plugins\RadiumWMPF\*\WeChatAppEx.exe' -and
    $_.CommandLine -notmatch '--type='
})
$results = @()
foreach ($root in $roots) {
    $renderers = @($processes | Where-Object {
        $_.ParentProcessId -eq $root.ProcessId -and $_.Name -eq 'WeChatAppEx.exe' -and
        $_.ExecutablePath -eq $root.ExecutablePath -and $_.CommandLine -match '--type=renderer'
    })
    $changed = $false
    if ($Apply -and $renderers.Count -ge $MinimumRendererCount) {
        # Recheck identity immediately before stopping only the embedded web
        # runtime. Never terminate Weixin, WXWork, or reset account storage.
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($root.ProcessId)"
        if ($current.CreationDate -ne $root.CreationDate -or
            $current.ExecutablePath -ne $root.ExecutablePath) { throw 'Runtime identity changed.' }
        & cmd.exe /d /c "taskkill.exe /PID $($root.ProcessId) /T /F >NUL 2>&1"
        # Chromium children may exit during taskkill's snapshot. Its nonzero
        # exit alone is not failure; verify the exact old process identities.
        $remaining = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ProcessId -eq $root.ProcessId -and $_.CreationDate -eq $root.CreationDate -or
            $_.Name -eq 'WeChatAppEx.exe' -and $_.ParentProcessId -eq $root.ProcessId -and
            $_.ExecutablePath -eq $root.ExecutablePath
        })
        if ($remaining.Count -gt 0) { throw 'Old web runtime processes remain.' }
        $changed = $true
    }
    $results += [ordered]@{ process_id=$root.ProcessId; renderer_count=$renderers.Count; reset=$changed }
}
foreach ($client in $clients) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($client.ProcessId)"
    if (-not $current -or $current.CreationDate -ne $client.CreationDate) { throw 'Client process changed.' }
}
[ordered]@{
    ok=$true; applied=[bool]$Apply; clients_preserved=$true
    observed_at=[DateTimeOffset]::Now.ToString('o'); runtimes=$results
} | ConvertTo-Json -Depth 4
exit 0
