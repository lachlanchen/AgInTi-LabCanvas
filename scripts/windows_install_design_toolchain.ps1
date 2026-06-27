param(
  [switch]$SkipLargeLaunchers,
  [switch]$InstallLabCanvasEditable = $true
)

$ErrorActionPreference = 'Continue'

function Install-WingetPackage {
  param(
    [Parameter(Mandatory=$true)][string]$Id,
    [Parameter(Mandatory=$true)][string]$Name,
    [int]$TimeoutSeconds = 900
  )

  Write-Host "== Installing $Name [$Id] =="
  $args = @(
    'install',
    '--id', $Id,
    '-e',
    '--accept-package-agreements',
    '--accept-source-agreements'
  )
  $p = Start-Process -FilePath 'winget' -ArgumentList $args -NoNewWindow -PassThru -Wait:$false
  $done = $p.WaitForExit($TimeoutSeconds * 1000)
  if (-not $done) {
    Write-Warning "Timed out installing $Name; stopping winget PID $($p.Id)"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    return $false
  }
  if ($p.ExitCode -ne 0) {
    Write-Warning "$Name installer exited with code $($p.ExitCode)"
    return $false
  }
  return $true
}

$packages = @(
  @{Id='OpenSCAD.OpenSCAD'; Name='OpenSCAD'; Timeout=900},
  @{Id='KiCad.KiCad'; Name='KiCad'; Timeout=1200},
  @{Id='BlenderFoundation.Blender'; Name='Blender'; Timeout=1200},
  @{Id='FreeCAD.FreeCAD'; Name='FreeCAD'; Timeout=1200},
  @{Id='Inkscape.Inkscape'; Name='Inkscape'; Timeout=900},
  @{Id='Graphviz.Graphviz'; Name='Graphviz'; Timeout=600},
  @{Id='ImageMagick.ImageMagick'; Name='ImageMagick'; Timeout=600},
  @{Id='CNRISTI.MeshLab'; Name='MeshLab'; Timeout=900},
  @{Id='Prusa3D.PrusaSlicer'; Name='PrusaSlicer'; Timeout=900},
  @{Id='Ultimaker.Cura'; Name='UltiMaker Cura'; Timeout=1200},
  @{Id='GodotEngine.GodotEngine'; Name='Godot'; Timeout=900},
  @{Id='OpenJS.NodeJS.LTS'; Name='Node.js LTS'; Timeout=600}
)

if (-not $SkipLargeLaunchers) {
  $packages += @(
    @{Id='EpicGames.EpicGamesLauncher'; Name='Epic Games Launcher'; Timeout=1200}
  )
}

$results = @()
foreach ($pkg in $packages) {
  $ok = Install-WingetPackage -Id $pkg.Id -Name $pkg.Name -TimeoutSeconds $pkg.Timeout
  $results += [PSCustomObject]@{
    Name = $pkg.Name
    Id = $pkg.Id
    Ok = $ok
  }
}

if ($InstallLabCanvasEditable) {
  Write-Host '== Installing LabCanvas Python package in editable mode =='
  python -m pip install -e .
}

Write-Host ''
Write-Host '== Install summary =='
$results | Format-Table -AutoSize

Write-Host ''
Write-Host 'Unity Hub note: if winget reports an installer hash mismatch, install manually from Unity or retry after winget metadata updates.'
Write-Host 'Open a new PowerShell after installation so GUI command aliases and PATH changes are visible.'
