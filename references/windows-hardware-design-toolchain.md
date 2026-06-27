# Windows Hardware Design Toolchain

This machine was prepared as a local AgInTi LabCanvas workstation for hardware design, PCB layout, CAD modeling, mesh cleanup, 3D printing, and render handoff.

## Installed / Prepared Tools

Package-managed installs completed:

- OpenSCAD `2021.01` - scriptable mechanical CAD.
- KiCad `10.0.3` - schematic and PCB layout.
- Blender `5.1.2` - 3D rendering and scene generation.
- FreeCAD `1.1.1` - parametric mechanical CAD.
- Inkscape `0.92.4` - SVG/vector editing; update attempt hung, so the existing install was kept.
- Graphviz `15.1.0` - graph/flowchart rendering.
- ImageMagick `7.1.2-26` - image conversion/compositing.
- MeshLab `2025.07` - mesh inspection and cleanup.
- PrusaSlicer `2.9.5` - 3D-print slicing.
- UltiMaker Cura `5.13.0` - 3D-print slicing.
- Godot `4.7` - lightweight interactive/engine visualization.
- Epic Games Launcher `1.3.189.0` - entry point for Unreal Engine installation.
- Node.js LTS - already installed and available.

Unity Hub was attempted through winget, but the installer hash did not match winget metadata. It was not installed because forcing a mismatched installer is not safe. Install Unity Hub manually from Unity or retry winget after metadata updates.

## PATH Note

Several GUI packages are installed but not visible to the current PowerShell session until a new terminal is opened or PATH is refreshed. Blender is usable directly at:

```text
C:\Program Files\Blender Foundation\Blender 5.1\blender.exe
```

## First Render

Editable scene spec:

```text
examples/labcanvas-hardware-studio.scene.json
```

Expected render output:

```text
examples/renders/labcanvas-hardware-studio.png
examples/renders/labcanvas-hardware-studio.blend
```

Command:

```powershell
$env:PYTHONPATH="src"
python -m agenticapp render-scene examples\labcanvas-hardware-studio.scene.json `
  --output-dir examples\renders `
  --blender-bin "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
```

Convenience wrapper:

```powershell
.\scripts\windows_render_hardware_studio.ps1
```

## Reproducible Windows Deployment Scripts

Install or refresh the Windows design stack:

```powershell
.\scripts\windows_install_design_toolchain.ps1
```

Skip large launchers such as Epic Games Launcher:

```powershell
.\scripts\windows_install_design_toolchain.ps1 -SkipLargeLaunchers
```

Check command availability and LabCanvas status:

```powershell
.\scripts\windows_labcanvas_doctor.ps1
```

These scripts are Windows-first equivalents of the previous Ubuntu-oriented setup flow. They rely on `winget`, `pip`, and the local source checkout.

## Methods Used In This Deployment

1. Installed the repository into `C:\Users\Administrator\Projects\AgInTi-LabCanvas`.
2. Used `winget` to install CAD/PCB/render tools.
3. Used `python -m pip install -e .` to expose the LabCanvas Python CLI from the source checkout.
4. Used `PYTHONPATH=src` plus `python -m agenticapp render-scene` for a deterministic local render.
5. Used Blender headless mode through the explicit path:

```text
C:\Program Files\Blender Foundation\Blender 5.1\blender.exe
```

6. Saved the editable scene spec and render outputs in `examples/`.

## Practical Role Split

- KiCad: exact PCB schematics, layout, DRC/ERC, Gerbers.
- OpenSCAD / FreeCAD: mechanical parts, mounts, adapters, enclosures.
- Blender: publication figures, exploded views, optical bench renders.
- MeshLab: clean imported STL/OBJ meshes.
- PrusaSlicer / Cura: manufacturing prep for 3D prints.
- Godot / Unity / Unreal: interactive lab visualization and simulation.
- Graphviz / ImageMagick / Inkscape: diagrams, SVG, and final figure polishing.
