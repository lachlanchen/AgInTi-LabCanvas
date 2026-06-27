param(
  [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = 'Continue'

Set-Location $RepoRoot

Write-Host '== AgInTi LabCanvas Windows doctor =='
Write-Host "Repo: $RepoRoot"
Write-Host ''

$commands = @(
  'python',
  'pip',
  'node',
  'npm',
  'git',
  'labcanvas',
  'blender',
  'openscad',
  'kicad',
  'freecad',
  'inkscape',
  'dot',
  'magick',
  'meshlab',
  'prusa-slicer',
  'cura',
  'godot'
)

Write-Host '== Command lookup =='
foreach ($cmd in $commands) {
  $found = Get-Command $cmd -ErrorAction SilentlyContinue
  if ($found) {
    "{0}`t{1}" -f $cmd, $found.Source
  } else {
    "{0}`tMISSING" -f $cmd
  }
}

Write-Host ''
Write-Host '== Common GUI executable fallbacks =='
$fallbacks = @(
  'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
  'C:\Program Files\KiCad\10.0\bin\kicad.exe',
  'C:\Program Files\OpenSCAD\openscad.exe',
  'C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe',
  'C:\Program Files\Graphviz\bin\dot.exe'
)

foreach ($path in $fallbacks) {
  if (Test-Path $path) {
    "FOUND`t$path"
  } else {
    "MISSING`t$path"
  }
}

Write-Host ''
Write-Host '== LabCanvas CLI doctor =='
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
python -m agenticapp doctor
