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
- `designs/cmount_threaded_reflector_assembly/`: newer two-part design with a 50 mm male-male C-mount tube, 20 mm threads on each end, and a top-open 20 x 20 x 20 mm reflector holder with a female threaded left socket.

## Research Notes

- `research/openhi_nature_step_notes.md`: inventory and inferred C-mount dimensions from the OpenHI/Nature STEP examples.
- `references/cmount-reflector-adapter-scale.md`: 1:1 scale table for the C-mount reflector adapter.
- `references/cmount-threaded-reflector-assembly-scale.md`: scale table and old A/B/C 4f branch evidence for the newer two-part reflector assembly.
- `references/cad-toolchain.md`: installed CAD tools, local Python CAD kernel, and render commands.
- `environment-cad-python.yml`: reproducible conda environment spec for CadQuery/build123d/OCP work.
- `../pcb/jlcpcb-jialichuang-automation.md`: JLCPCB/Jialichuang order automation research and safe automation boundary.

## Scale Convention

CAD source files are authored in millimetres at 1:1 scale. For the C-mount reflector adapter, the expected slicer/CAD bounding box is `49.5 x 26 x 26 mm`. Tune thread fit by changing the named thread parameters, not by scaling the whole model.

Current verified render/export path:

```bash
openscad -o cad/designs/cmount_reflector_adapter/artifacts/cmount_reflector_adapter.stl cad/designs/cmount_reflector_adapter/cmount_reflector_adapter.scad
blender --background --python cad/designs/cmount_reflector_adapter/blender_render.py
```

## Preferred Shapr3D Export Formats

For editable mechanical work, export **STEP** first. STEP preserves solid geometry and is the best input for FreeCAD, OpenSCAD-adjacent workflows, KiCad 3D models, and future machining checks.

Also export these when useful:

- `3MF` for 3D-print slicers with units/material metadata.
- `STL` for quick print previews only; it is mesh-only and not ideal for editing.
- `DXF from sketch` for flat mounting plates, hole patterns, and PCB outlines.
- `SVG` or `PDF` for documentation drawings.

Avoid using only `.shapr3d`, `.obj`, `.glb`, or image exports when the part must be dimensionally edited later.
