# CAD Workspace

This folder collects local optical-mechanical reference CAD, parametric adapter designs, and manufacturing notes for AppAutoAction-assisted experiment hardware.

## Local Reference STEP Sets

The current local examples were copied from:

- `/home/lachlan/Downloads/OpenHI_STEP.zip`
- `/home/lachlan/Downloads/Nature_STEP.zip`

They are unpacked locally under:

- `cad/sources/`
- `cad/extracted/OpenHI_STEP/`
- `cad/extracted/Nature_STEP/`

These raw zip and STEP dumps are intentionally ignored by git. Keep them local unless a smaller, cleaned reference file is explicitly approved for publication.

## Designs

- `designs/cmount_reflector_adapter/`: printable C-mount male to reflector-cube adapter draft. One end uses a printer-compensated external C-mount-like thread; the other end is a 20 x 20 x 20 mm internal reflector chamber with 3 mm walls.

## Research Notes

- `research/openhi_nature_step_notes.md`: inventory and inferred C-mount dimensions from the OpenHI/Nature STEP examples.
- `../pcb/jlcpcb-jialichuang-automation.md`: JLCPCB/Jialichuang order automation research and safe automation boundary.

## Preferred Shapr3D Export Formats

For editable mechanical work, export **STEP** first. STEP preserves solid geometry and is the best input for FreeCAD, OpenSCAD-adjacent workflows, KiCad 3D models, and future machining checks.

Also export these when useful:

- `3MF` for 3D-print slicers with units/material metadata.
- `STL` for quick print previews only; it is mesh-only and not ideal for editing.
- `DXF from sketch` for flat mounting plates, hole patterns, and PCB outlines.
- `SVG` or `PDF` for documentation drawings.

Avoid using only `.shapr3d`, `.obj`, `.glb`, or image exports when the part must be dimensionally edited later.
