# OpenHI A/B/C Exact Parametric Baseline

This project regenerates the complete current geometry of `A.step`, `B.step`, and `C.step` without changing any pivot, pitch, thread, chamfer, hole, lens seat, body placement, or compound topology.

The `.shapr` archive is used to confirm the imported-body history and naming. The flattened STEP B-reps remain the exact geometry authority on Ubuntu.

## Original Editable Parameters

- Thread pitch: `0.8 mm`.
- Radial tooth height: `0.4 mm` (`0.8 mm` diameter difference).
- A top male pivot/crest: `29.8 / 30.6 mm`.
- B lens male pivot/crest: `29.6 / 30.4 mm`.
- B camera male pivot/crest: `24.4 / 25.2 mm`.
- C lens male pivot/crest: `29.6 / 30.4 mm`.
- C camera male pivot/crest: `24.4 / 25.2 mm`.

These values are named command-line parameters in the builder. The current run leaves all of them unchanged. When all targets equal the source values, the builder preserves every original solid and only performs a clean STEP round trip. A future variant may change one pivot and rebuild only that localized tooth/root interface.

## Direct Files

| Part | Exact editable STEP | Print-ready STEP | Print-ready STL | Print-ready 3MF | Full render |
| --- | --- | --- | --- | --- | --- |
| A | `cad/designs/openhi_abc_exact_parametric_baseline/USE_THIS_OpenHI_A_exact_current_geometry.step` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_A_exact_current_geometry.step` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_A_exact_current_geometry.stl` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_A_exact_current_geometry.3mf` | `cad/designs/openhi_abc_exact_parametric_baseline/artifacts/OpenHI_A_exact_current_geometry_render.png` |
| B | `cad/designs/openhi_abc_exact_parametric_baseline/USE_THIS_OpenHI_B_exact_current_geometry.step` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_B_exact_current_geometry.step` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_B_exact_current_geometry.stl` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_B_exact_current_geometry.3mf` | `cad/designs/openhi_abc_exact_parametric_baseline/artifacts/OpenHI_B_exact_current_geometry_render.png` |
| C | `cad/designs/openhi_abc_exact_parametric_baseline/USE_THIS_OpenHI_C_exact_current_geometry.step` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_C_exact_current_geometry.step` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_C_exact_current_geometry.stl` | `cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_C_exact_current_geometry.3mf` | `cad/designs/openhi_abc_exact_parametric_baseline/artifacts/OpenHI_C_exact_current_geometry_render.png` |

## Validation

- A: `3` solids, `24` faces, bbox `[40.0000002, 40.0000002, 50.0000001]` mm, volume delta `1.2859e-05` mm^3, all checks `True`.
- B: `4` solids, `41` faces, bbox `[40.0, 40.0, 54.400000085]` mm, volume delta `0.011412917` mm^3, all checks `True`.
- C: `4` solids, `38` faces, bbox `[54.0000001, 40.0, 40.0]` mm, volume delta `2.0741e-05` mm^3, all checks `True`.

The STEP files are authoritative editable B-reps. STL and 3MF are deterministic tessellations of those regenerated B-reps; they are not mathematical B-rep formats.

Use `USE_THIS_*.step` for Shapr3D editing. Use `PRINT_THIS_*.3mf` or `PRINT_THIS_*.stl` in Qidi Studio. The print-only body unions the source tooth/root solids into one valid watertight solid, is rigidly moved to `Z=0`, and packages exactly one 3MF model/build object. C is rotated from its assembly X axis onto print Z. The exact editable STEP remains an unchanged multi-solid B-rep.

## Rebuild

```bash
cad/.conda/cad-python/bin/python3.11 cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py
blender --background --python cad/designs/openhi_abc_exact_parametric_baseline/render_openhi_abc_exact_parametric_baseline.py
cad/.conda/cad-python/bin/python3.11 cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py --sync-only --run-name run-2-qidi-single-object-build-plate-20260816T135323Z
```

Example future variant (not used for this baseline):

```bash
cad/.conda/cad-python/bin/python3.11 cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py --b-lens-pivot 29.8 --run-name run-3-b-lens-29p8-YYYYMMDDTHHMMSSZ
```

Use a new run name for every physical geometry change. Never overwrite the original extracted STEP sources.
