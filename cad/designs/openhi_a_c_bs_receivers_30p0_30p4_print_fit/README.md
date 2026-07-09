# OpenHI A+C+BS Shapr-Friendly 30.0/30.4 Print Fit

## Use This File

Import this root-level STEP first:

`USE_THIS_openhi_a_c_bs_receivers_30p0_30p4_print_fit.step`

It is the final directly usable assembly with the repaired 30.0/30.4 receiver ring-groove preview. The other STEP files in `artifacts/` are references, smooth/editable variants, or cutter/sleeve parts.

This folder contains a Shapr-friendly print-fit variant of the OpenHI A+C+BS receiver body. It keeps the original exported STEP body and replaces only the fragile receiver/thread zones with clean analytic sleeves.

## Why This Rebuild Exists

The earlier edited STEP was OCCT-valid, but Shapr3D spent a long time repairing it and then dropped thread faces or showed transparent broken regions. The problem was the combination of imported helical B-spline thread faces and local boolean edits near the BS pocket.

This version does not approximate the whole BS body. It preserves the original outer body, BS slope/slot area, lens seat, pin holes, and chamfers, then heals only the two 30 mm receiver zones. The default file uses simple ring-groove thread previews. The smooth file has no thread preview and is the safest one for Shapr editing or physical tapping.

Detailed repair notes: [openhi-shapr3d-step-import-repair.md](../../../references/openhi-shapr3d-step-import-repair.md).

## Geometry Basis

- Original source bbox: `40.0000002 x 40.0000002 x 84.900000204 mm`
- Rebuilt bbox: `40.086138004 x 40.073705286 x 84.951422064 mm`
- Rebuilt solids: `1`; OCCT valid: `True`
- Smooth editable solids: `1`; OCCT valid: `True`
- Original surface counts: `{'GeomAbs_SurfaceType.GeomAbs_OffsetSurface': 1, 'bspline': 6, 'cone': 3, 'cylinder': 15, 'plane': 27}`
- Rebuilt surface counts: `{'GeomAbs_SurfaceType.GeomAbs_OffsetSurface': 1, 'cone': 3, 'cylinder': 47, 'plane': 60}`
- Smooth editable surface counts: `{'GeomAbs_SurfaceType.GeomAbs_OffsetSurface': 1, 'cone': 3, 'cylinder': 15, 'plane': 28}`
- Fit change: receiver pilots use `30.0 mm`; ring-groove previews cut to `30.4 mm`.
- Thread policy: original helical B-spline thread faces are removed from the repaired receiver zones for Shapr import stability.

## Recommended Files

- Shapr import with visible ring-groove preview: `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit.step`
- Shapr edit/tap-ready smooth version: `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_smooth_editable.step`
- Sleeve references: `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_lower_receiver_healing_sleeve.step`, `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_bs_receiver_healing_sleeve.step`
- Ring cutter references: `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_lower_ring_groove_cutters.step`, `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_bs_ring_groove_cutters.step`

## Artifacts

| Artifact | Path |
| --- | --- |
| smooth_editable_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_smooth_editable.step` |
| smooth_editable_stl | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_smooth_editable.stl` |
| assembly_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit.step` |
| assembly_stl | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit.stl` |
| lower_receiver_healing_sleeve_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_lower_receiver_healing_sleeve.step` |
| bs_receiver_healing_sleeve_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_bs_receiver_healing_sleeve.step` |
| lower_ring_groove_cutters_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_lower_ring_groove_cutters.step` |
| bs_ring_groove_cutters_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_bs_ring_groove_cutters.step` |
| render_png | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_render.png` |
| receiver_detail_render_png | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_receiver_detail_render.png` |
| blend | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit.blend` |
| manifest_json | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/build_openhi_a_c_bs_receivers_30p0_30p4_print_fit.py
blender --background --python cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/render_openhi_a_c_bs_receivers_30p0_30p4_print_fit.py
```
