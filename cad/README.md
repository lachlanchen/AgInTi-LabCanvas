# CAD Workspace

This folder collects local optical-mechanical reference CAD, parametric adapter designs, and manufacturing notes for AgInTi LabCanvas-assisted experiment hardware.

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
- `designs/cmount_threaded_reflector_assembly/`: two-part design with versioned artifacts. Current v2 has a 50 mm male-male C-mount tube, 15 mm male threads on each end, 28.4 mm thick center body, and a top-open 20.4 x 20.4 x 20.4 mm reflector holder with a max 20 mm internal female thread. The v2 artifacts are split into named run folders; see `designs/cmount_threaded_reflector_assembly/artifacts/v2_15mm_threads_print_fit/RUNS.md` for the single-file copy recommendation.

## Research Notes

- `tools/optical_reference_downloader.py`: reusable optical CAD reference downloader for Hengyang and Thorlabs parts, plus TeX/PDF report generation.
- `references/OPTICAL_REFERENCE_DOWNLOADER.md`: exact tools, endpoints, commands, and agent workflow for fast optical setup reference collection.
- `references/thorlabs-optics/`: local Thorlabs common 30 mm cage starter references with STEP, CAD PDF, CAD DXF, product image, and product JSON files.
- `reports/optical-reference-quick-design/optical_reference_quick_design.pdf`: compiled quick-design report for the current Lumileds holder and optical reference library.
- `research/openhi_nature_step_notes.md`: inventory and inferred C-mount dimensions from the OpenHI/Nature STEP examples.
- `references/cmount-reflector-adapter-scale.md`: 1:1 scale table for the C-mount reflector adapter.
- `references/cmount-threaded-reflector-assembly-scale.md`: scale table and old A/B/C 4f branch evidence for the newer two-part reflector assembly.
- `references/openhi-print-fit-and-thread-reference.md`: measured old STEP mating table for the 24.4/24.8 thread fit, 29.6 larger thread family, 40 mm square modules, and 0.4 mm printed receiver clearance rule.
- `references/cad-toolchain.md`: installed CAD tools, local Python CAD kernel, and render commands.
- `environment-cad-python.yml`: reproducible conda environment spec for CadQuery/build123d/OCP work.
- `../pcb/jlcpcb-jialichuang-automation.md`: JLCPCB/Jialichuang order automation research and safe automation boundary.

## Scale Convention

CAD source files are authored in millimetres at 1:1 scale. For the C-mount reflector adapter, the expected slicer/CAD bounding box is `49.5 x 26 x 26 mm`. For the current threaded reflector assembly v2, the expected assembly bounding box is `83.4 x 34.0 x 31.2 mm`. Tune thread fit by changing the named thread, socket, or pocket parameters, not by scaling the whole model.

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
