# OpenHI Lens B Holder Shapr Exact Regeneration

This folder regenerates the OpenHI `Lens B holder.step` as an exact B-rep reference.

The source Shapr file confirms the object mapping:

- Shapr folder: `Lens B holder`
- Shapr import node: `1018368` / `Import "BS lateral.step"`
- Shapr primary label: `Lens B holder chopped (2)* (1)`
- Imported body ID: `248`

Because `Nature.shapr` stores this holder as an imported Parasolid body, not as editable native Shapr sketches/features, the exact Ubuntu path is to use the exported STEP B-rep and preserve its geometry. Use this as the baseline before changing only the larger female receiver/thread fit.

## Geometry Summary

- Bounding box: `40.7340002 x 40.7340002 x 85.367000205 mm`
- Solids: `1`
- Faces: `35`
- Volume: `46599.74809551 mm^3`
- Surface counts: `{'GeomAbs_SurfaceType.GeomAbs_OffsetSurface': 1, 'bspline': 2, 'cone': 4, 'cylinder': 20, 'plane': 8}`

## Proof Of Concept Verification

This proof of concept preserves the original STEP boundary representation instead of rebuilding an approximate parametric clone.

- Regenerated bounding box: `40.7340002 x 40.7340002 x 85.367000205 mm`
- Bounding-box absolute difference: `[0.0, 0.0, 0.0] mm`
- Face count unchanged: `True`
- Solid count unchanged: `True`
- Volume absolute difference after STEP round trip: `0.456415251 mm^3`
- Area absolute difference after STEP round trip: `0.042693344 mm^2`
- Surface type counts unchanged: `True`
- Small oblique end sink face count unchanged: `True`
- Chamfer cone face count unchanged: `True`

Use the regenerated STEP as the exact baseline for later variants. If the next variant changes the female receiver to `25.4 mm`, keep this folder unchanged and create a sibling folder.

## Thread And Chamfer Evidence

- Small oblique end sink/counterbore faces are preserved:
  `[(1, 2.0), (5, 3.0)]` as `(face, diameter_mm)`.
- Side pin holes are preserved:
  `[(7, 1.6), (10, 1.6)]` as `(face, diameter_mm)`.
- Chamfer cone face count: `4`.
- Larger lens-thread axis is along `Z` around `(x=254.633, y=210.0)`.
- Repeated cylindrical tooth faces use radius about `15.1 mm` / diameter `30.2 mm`.
- Two large B-spline faces span the helical threaded zone, about `31 mm` in X/Y and `8.15 mm` in Z.
- Conical end/chamfer faces are preserved by the B-rep export; their measured semi-angle is about `0.7854 rad`.

## Artifacts

| Artifact | Path |
| --- | --- |
| regenerated_step | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen.step` |
| regenerated_stl | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen.stl` |
| inspection_cutaway_step | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen_inspection_cutaway.step` |
| inspection_cutaway_stl | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen_inspection_cutaway.stl` |
| render_png | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen_render.png` |
| thread_detail_render_png | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen_thread_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/openhi_lens_b_holder_shapr_exact_regen.blend` |
| manifest_json | `cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_lens_b_holder_shapr_exact_regen/build_openhi_lens_b_holder_shapr_exact_regen.py
blender --background --python cad/designs/openhi_lens_b_holder_shapr_exact_regen/render_openhi_lens_b_holder_shapr_exact_regen.py
```

## Next Editable Variant

For the next printer-fit experiment, create a sibling parametric/surgical variant from this exact baseline and change only the requested female receiver/thread construction, such as a normal `25.4 mm` C-mount-sized receiver. Keep this proof-of-concept folder unchanged.
