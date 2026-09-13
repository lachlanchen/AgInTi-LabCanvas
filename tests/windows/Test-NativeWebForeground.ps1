param([string]$HelperPath)
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($HelperPath,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors.Message -join '; ') }
$function=$ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Test-NativeWebForeground'
}, $true)
Invoke-Expression $function.Extent.Text
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    $key=[int]($Filter -replace 'ProcessId=','')
    return $script:Rows[$key]
}
$script:TargetApp='wechat'
$session=[System.Diagnostics.Process]::GetCurrentProcess().SessionId
$base=[datetime]'2026-01-01'
$window=[pscustomobject]@{ ProcessId=10 }
function Reset-Rows {
    $script:Rows=@{
        10=[pscustomobject]@{ ProcessId=10; ParentProcessId=1; Name='Weixin.exe'; CreationDate=$base; SessionId=$session }
        20=[pscustomobject]@{ ProcessId=20; ParentProcessId=10; Name='WeChatAppEx.exe'; CreationDate=$base.AddSeconds(1); SessionId=$session; ExecutablePath='C:\Users\owner\AppData\Roaming\Tencent\xwechat\xplugin\runtime\WeChatAppEx.exe' }
        30=[pscustomobject]@{ ProcessId=30; ParentProcessId=20; Name='WeChatAppEx.exe'; CreationDate=$base.AddSeconds(2); SessionId=$session; ExecutablePath='C:\Users\owner\AppData\Roaming\Tencent\xwechat\xplugin\runtime\WeChatAppEx.exe' }
    }
}
Reset-Rows
if (-not (Test-NativeWebForeground 30 $window)) { throw 'Exact descendant rejected.' }
if (Test-NativeWebForeground 99 $window) { throw 'Unknown process accepted.' }
foreach ($case in @('other_app','foreign_binary','other_session','wrong_parent','reused_pid','cycle')) {
    Reset-Rows
    switch ($case) {
        'other_app' { $Rows[30].ExecutablePath=$Rows[30].ExecutablePath.Replace('xwechat','WXWork') }
        'foreign_binary' { $Rows[30].Name='chrome.exe' }
        'other_session' { $Rows[30].SessionId=$session+1 }
        'wrong_parent' { $Rows[20].ParentProcessId=99 }
        'reused_pid' { $Rows[20].CreationDate=$base.AddDays(1) }
        'cycle' { $Rows[20].ParentProcessId=30 }
    }
    if (Test-NativeWebForeground 30 $window) { throw "Unsafe foreground accepted: $case" }
}
Write-Output 'PASS: native child accepted; seven unrelated/stale/cyclic cases rejected; no GUI input.'
