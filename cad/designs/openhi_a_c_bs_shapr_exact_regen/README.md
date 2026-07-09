# OpenHI A+C+BS Shapr Exact Regeneration

This folder regenerates `cad/extracted/OpenHI_STEP/A+ C + BS.step` as the exact B-rep baseline before any thread-fit edits.

The Shapr workspace confirms this part belongs to the imported OpenHI/BS lateral group. It does not expose a replayable native feature tree for this body on Ubuntu, so the exact rebuild preserves the exported STEP boundary representation and records measured feature evidence.

## Geometry Summary

- Bounding box: `40.0000002 x 40.0000002 x 84.900000204 mm`
- Solids: `1`
- Faces: `52`
- Volume: `46328.645325239 mm^3`
- Surface counts: `{'GeomAbs_SurfaceType.GeomAbs_OffsetSurface': 1, 'bspline': 6, 'cone': 3, 'cylinder': 15, 'plane': 27}`

## Thread Evidence

Both receiver starts in the exported STEP measure as 30.2 mm diameter surfaces:

- Bottom/away-from-BS receiver, Z axis: `[(0, 30.2, [255.0, 210.0, 545.0], [0.0, 0.0, 1.0]), (51, 30.2, [255.0, 210.0, 545.0], [0.0, 0.0, 1.0])]`.
- BS/B-side receiver, X axis: `[(17, 30.2, [305.0, 210.0, 600.0], [-1.0, 0.0, 0.0])]`.
- Bottom helical B-spline faces: `[44, 45, 46]`.
- BS/B-side helical B-spline faces: `[48, 50]`.
- In this STEP there is no measured evidence that the BS/B-side receiver was already smaller than the bottom receiver; both expose 30.2 mm cylindrical start/root faces.

Related preserved features:

- Center bore faces: `[(2, 24.0)]`.
- Lens seat faces: `[(40, 25.5)]`.
- 45 degree chamfer cone count: `3`.
- Side pin holes: `[(21, 1.6), (23, 1.6)]`.
- Oblique holes/counterbores: `[(20, 2.0), (31, 1.4), (33, 1.4), (35, 1.4), (37, 1.4)]`.

## Verification

- Regenerated bounding box: `40.0000002 x 40.0000002 x 84.900000204 mm`
- Bounding-box absolute difference: `[0.0, 0.0, 0.0] mm`
- Face count unchanged: `True`
- Solid count unchanged: `True`
- Surface type counts unchanged: `True`
- Volume absolute difference after STEP round trip: `4.6652e-05 mm^3`

## Artifacts

| Artifact | Path |
| --- | --- |
| regenerated_step | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen.step` |
| regenerated_stl | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen.stl` |
| inspection_cutaway_step | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen_inspection_cutaway.step` |
| inspection_cutaway_stl | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen_inspection_cutaway.stl` |
| render_png | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen_render.png` |
| thread_detail_render_png | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen_thread_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/openhi_a_c_bs_shapr_exact_regen.blend` |
| manifest_json | `cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_a_c_bs_shapr_exact_regen/build_openhi_a_c_bs_shapr_exact_regen.py
blender --background --python cad/designs/openhi_a_c_bs_shapr_exact_regen/render_openhi_a_c_bs_shapr_exact_regen.py
```

## Next Variant

Keep this folder unchanged. For the print-fit experiment, create a sibling variant that changes only the two OpenHI 30 mm female receiver starts from 30.2 mm to 30.0 mm while preserving the outer body, BS slope area, lens seat, side holes, and chamfers.
