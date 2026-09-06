param(
    [string]$Setup = 'C:\LabCanvas\Displays\setup',
    [switch]$InstallVnc
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
if ($env:COMPUTERNAME -ne 'TINY11-KVM') { throw 'Dedicated Tiny11 VM only.' }

function Assert-Signature([string]$Path, [string]$Publisher) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike $Publisher) {
        throw "Unexpected or invalid signature: $Path"
    }
    return $signature
}

if ($InstallVnc) {
    Assert-Signature "$Setup\tightvnc.msi" '*GlavSoft*' | Out-Null
    # No LAN listener, firewall exceptions, disconnect lock, or logoff.
    $arguments = @('/i', "$Setup\tightvnc.msi", '/quiet', '/norestart',
        'ADDLOCAL=Server', 'SERVER_REGISTER_AS_SERVICE=1',
        'SERVER_ADD_FIREWALL_EXCEPTION=0', 'SERVER_ALLOW_SAS=0',
        'SET_LOOPBACKONLY=1', 'VALUE_OF_LOOPBACKONLY=1',
        'SET_ALLOWLOOPBACK=1', 'VALUE_OF_ALLOWLOOPBACK=1',
        'SET_ACCEPTHTTPCONNECTIONS=1', 'VALUE_OF_ACCEPTHTTPCONNECTIONS=0',
        'SET_USEVNCAUTHENTICATION=1', 'VALUE_OF_USEVNCAUTHENTICATION=0',
        'SET_USECONTROLAUTHENTICATION=1', 'VALUE_OF_USECONTROLAUTHENTICATION=0',
        'SET_ALWAYSSHARED=1', 'VALUE_OF_ALWAYSSHARED=1',
        'SET_DISCONNECTACTION=1', 'VALUE_OF_DISCONNECTACTION=0')
    $p = Start-Process msiexec.exe -ArgumentList $arguments -Wait -PassThru
    if ($p.ExitCode -notin @(0,3010)) { throw "VNC installer exit $($p.ExitCode)" }
    Get-Service tvnserver | Select-Object Name, Status | ConvertTo-Json -Compress
    exit
}

$existing = @(Get-CimInstance Win32_PnPEntity |
    Where-Object { $_.PNPClass -eq 'Display' -and $_.HardwareID -contains 'Root\MttVDD' })
if ($existing.Count -gt 0) {
    $existing | Select-Object Name, Status, PNPDeviceID | ConvertTo-Json -Compress
    exit
}
Expand-Archive "$Setup\vdd.zip" "$Setup\vdd" -Force
Expand-Archive "$Setup\nefcon.zip" "$Setup\nefcon" -Force
$driver = "$Setup\vdd\VirtualDisplayDriver"
$signature = Assert-Signature "$driver\mttvdd.cat" '*SignPath Foundation*'
Assert-Signature "$Setup\nefcon\x64\nefconw.exe" '*Nefarius Software Solutions*' | Out-Null

# Trust only the verified package signer, not every certificate from a bundle.
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store('TrustedPublisher','LocalMachine')
$store.Open('ReadWrite')
try { $store.Add($signature.SignerCertificate) } finally { $store.Close() }
New-Item -ItemType Directory -Force C:\VirtualDisplayDriver | Out-Null
$settingsPath = 'C:\VirtualDisplayDriver\vdd_settings.xml'
if (Test-Path $settingsPath) { throw 'Existing VDD settings require review before replacement.' }
[xml]$settings = Get-Content "$driver\vdd_settings.xml"
$settings.vdd_settings.monitors.count = '1'
# Add one right-hand screen; retain the original QEMU display and its login.
$resolutions = $settings.SelectSingleNode('/vdd_settings/resolutions')
$resolutions.RemoveAll()
$resolution = $settings.CreateElement('resolution')
foreach ($pair in @(@('width','1280'),@('height','800'),@('refresh_rate','30'))) {
    $node = $settings.CreateElement($pair[0]); $node.InnerText = $pair[1]
    [void]$resolution.AppendChild($node)
}
[void]$resolutions.AppendChild($resolution)
$globalRates = $settings.SelectSingleNode('/vdd_settings/global')
$globalRates.RemoveAll()
$rate = $settings.CreateElement('g_refresh_rate'); $rate.InnerText = '30'
[void]$globalRates.AppendChild($rate)
$settings.Save($settingsPath)
$p = Start-Process "$Setup\nefcon\x64\nefconw.exe" -ArgumentList @('install', "$driver\MttVDD.inf", 'Root\MttVDD') -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Driver installer exit $($p.ExitCode)" }
# Bind the signed package as well as creating its root-enumerated device node.
pnputil /add-driver "$driver\MttVDD.inf" /install
if ($LASTEXITCODE -ne 0) { throw "Driver binding exit $LASTEXITCODE" }
Start-Sleep -Seconds 5
Get-PnpDevice -Class Display | Select-Object FriendlyName, Status, InstanceId | ConvertTo-Json -Compress
