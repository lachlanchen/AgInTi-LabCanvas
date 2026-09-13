param(
    [switch]$InstallMissingEdge,
    [string]$ExpectedComputer = 'LABCANVAS-PC',
    [string]$LogDirectory = 'C:\LabCanvas\BrowserRepair'
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) {
    throw 'Unexpected computer; refusing browser repair.'
}

if (-not ('LabCanvasBrowser.Associations' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace LabCanvasBrowser {
    public static class Associations {
        [DllImport("shlwapi.dll", CharSet=CharSet.Unicode)]
        private static extern int AssocQueryString(uint flags, uint str,
            string assoc, string extra, StringBuilder output, ref uint length);
        public static string Executable(string scheme) {
            uint length = 0;
            // ASSOCF_IS_PROTOCOL, ASSOCSTR_EXECUTABLE: use Shell resolution,
            // not ad-hoc parsing of quoted registry commands.
            AssocQueryString(0x1000, 2, scheme, "open", null, ref length);
            if (length == 0 || length > 32768) return null;
            var output = new StringBuilder((int)length);
            return AssocQueryString(0x1000, 2, scheme, "open", output, ref length) == 0
                ? output.ToString() : null;
        }
    }
}
'@
}

function Get-BrowserAssociations {
    foreach ($scheme in @('http', 'https')) {
        $choice = Get-ItemProperty (
            "HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\$scheme\UserChoice"
        ) -ErrorAction SilentlyContinue
        $exe = [LabCanvasBrowser.Associations]::Executable($scheme)
        [pscustomobject]@{
            scheme = $scheme
            prog_id = $choice.ProgId
            executable = $exe
            executable_exists = [bool]($exe -and (Test-Path -LiteralPath $exe -PathType Leaf))
        }
    }
}

$before = @(Get-BrowserAssociations)
$installed = $false
$installExitCode = $null
if ($InstallMissingEdge -and @($before | Where-Object { -not $_.executable_exists }).Count) {
    if (@($before | Where-Object { $_.prog_id -and $_.prog_id -ne 'MSEdgeHTM' }).Count) {
        throw 'A different browser was selected; inspect it instead of replacing the user preference.'
    }
    $winget = (Get-Command winget.exe -ErrorAction Stop).Source
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    & $winget install --id Microsoft.Edge --exact --source winget --silent `
        --accept-source-agreements --accept-package-agreements --disable-interactivity `
        --log (Join-Path $LogDirectory 'edge-install.log') |
        Out-File (Join-Path $LogDirectory 'winget-output.log') -Encoding utf8
    $installExitCode = $LASTEXITCODE
    if ($installExitCode -notin @(0, 3010)) {
        throw "Edge installation failed (exit $installExitCode); inspect $LogDirectory."
    }
    $installed = $true
}
$after = @(Get-BrowserAssociations)
$result = [ordered]@{
    ok = (@($after | Where-Object { -not $_.executable_exists }).Count -eq 0)
    observed_at = [DateTimeOffset]::Now.ToString('o')
    installed = $installed
    installer_exit_code = $installExitCode
    before = $before
    after = $after
}
$result | ConvertTo-Json -Depth 5
if ($InstallMissingEdge -and -not $result.ok) {
    throw 'A default browser handler is still missing. Use Windows Default apps; no UserChoice hashes were modified.'
}
