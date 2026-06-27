param(
  [string]$Spec = 'examples\labcanvas-hardware-studio.scene.json',
  [string]$OutputDir = 'examples\renders',
  [string]$BlenderBin = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RepoRoot

if (-not $BlenderBin) {
  $cmd = Get-Command blender -ErrorAction SilentlyContinue
  if ($cmd) {
    $BlenderBin = $cmd.Source
  } elseif (Test-Path 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe') {
    $BlenderBin = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
  } else {
    throw 'Blender executable not found. Install Blender or pass -BlenderBin.'
  }
}

$env:PYTHONPATH = Join-Path $RepoRoot 'src'

python -m agenticapp render-scene $Spec `
  --output-dir $OutputDir `
  --blender-bin $BlenderBin
