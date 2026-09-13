param([string]$SourcePath)
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $SourcePath, [ref]$tokens, [ref]$errors
)
if ($errors.Count) { throw 'Placement script failed to parse.' }
$function = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Select-AppPlacementWindows'
}, $true)
if (-not $function) { throw 'Placement selector is missing.' }
Invoke-Expression $function.Extent.Text
$main = [pscustomobject]@{ ClassName = 'WeWorkWindow' }
$settings = [pscustomobject]@{ ClassName = 'ConfigWindow' }
$popup = [pscustomobject]@{ ClassName = 'PopupMenu' }
$login = [pscustomobject]@{ ClassName = 'LoginWindow' }
$cases = @(
    @{ App = 'WeCom'; Windows = @($settings, $popup, $main); Expected = @($main) },
    @{ App = 'WeCom'; Windows = @($main); Expected = @($main) },
    @{ App = 'WeCom'; Windows = @($login); Expected = @($login) },
    @{ App = 'WeChat'; Windows = @($login); Expected = @($login) },
    @{ App = 'WeCom'; Windows = @(); Expected = @() }
)
foreach ($case in $cases) {
    $actual = @(Select-AppPlacementWindows -AppName $case.App -Windows $case.Windows)
    if ($actual.Count -ne $case.Expected.Count) { throw 'Unexpected placement count.' }
    for ($i = 0; $i -lt $actual.Count; $i++) {
        if (-not [object]::ReferenceEquals($actual[$i], $case.Expected[$i])) {
            throw 'Placement selected a popup or changed a window identity.'
        }
    }
}
Write-Output "Passed $($cases.Count) window-selection cases without GUI input."
