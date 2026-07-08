# OpenHI Lens C Holder Shapr Exact Regeneration

This folder regenerates `cad/extracted/OpenHI_STEP/Lens C holder.step` as an exact B-rep proof of concept.

The source STEP contains two solids: `Thread BS` and `T branch head (1)`. `Nature.shapr` stores the corresponding Lens C holder pieces as imported Parasolid bodies, so this exact regeneration preserves the exported STEP boundary representation rather than rebuilding an approximate feature tree.

## Geometry Summary

- Bounding box: `50.000000204 x 40.0000002 x 40.0000002 mm`
- Solids: `2`
- Faces: `36`
- Volume: `30806.728183238 mm^3`
- Surface counts: `{'bspline': 4, 'cone': 4, 'cylinder': 23, 'plane': 5}`

## Proof Of Concept Verification

- Regenerated bounding box: `50.000000204 x 40.0000002 x 40.0000002 mm`
- Bounding-box absolute difference: `[0.0, 0.0, 0.0] mm`
- Face count unchanged: `True`
- Solid count unchanged: `True`
- Surface type counts unchanged: `True`
- Volume absolute difference after STEP round trip: `0.007772615 mm^3`

## Thread And Chamfer Evidence

- `Thread BS` cylindrical thread faces: `[(2, 29.8), (6, 29.8), (7, 29.8), (8, 29.8), (9, 29.8), (10, 29.8), (11, 29.8), (12, 29.8), (16, 29.8)]` as `(face, diameter_mm)`.
- Positive-X receiver thread cylindrical faces: `[(18, 30.2), (26, 30.2), (27, 30.2), (28, 30.2), (29, 30.2), (30, 30.2), (31, 30.2), (32, 30.2), (33, 30.2), (34, 30.2), (35, 30.2)]` as `(face, diameter_mm)`.
- Positive-X receiver helical B-spline faces: `[24, 25]`.
- 45 degree chamfer cone face count: `4`.
- Center bore faces: `[(14, 24.0)]` as `(face, diameter_mm)`.

## Artifacts

| Artifact | Path |
| --- | --- |
| regenerated_step | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen.step` |
| regenerated_stl | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen.stl` |
| inspection_cutaway_step | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen_inspection_cutaway.step` |
| inspection_cutaway_stl | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen_inspection_cutaway.stl` |
| render_png | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen_render.png` |
| receiver_detail_render_png | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen_receiver_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/openhi_lens_c_holder_shapr_exact_regen.blend` |
| manifest_json | `cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_lens_c_holder_shapr_exact_regen/build_openhi_lens_c_holder_shapr_exact_regen.py
blender --background --python cad/designs/openhi_lens_c_holder_shapr_exact_regen/render_openhi_lens_c_holder_shapr_exact_regen.py
```

## Variant Notes

Keep this exact proof-of-concept folder unchanged. `openhi_lens_c_holder_receiver_25p4` is only a C-mount-sized experiment. The corrected OpenHI Lens C print-fit change is `openhi_lens_c_holder_receiver_30p0_30p4_print_fit`, which keeps the 30 mm family and tightens the positive-X receiver to a 30.0 mm pilot with a 30.4 mm groove cutter.
