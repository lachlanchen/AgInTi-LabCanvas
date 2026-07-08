# OpenHI Lens B Holder Receiver 30.0/30.4 Print Fit

This is a sibling variant of the exact Lens B holder regeneration. It keeps the original STEP-derived body and changes only the positive-Z OpenHI female receiver from the old 30.2 mm start/root to a tighter 30.0 mm pilot with a 30.4 mm groove cutter.

## Thread Definition

- Female smooth pilot/start diameter: `30.0 mm`
- Female groove/thread-cutter max diameter: `30.4 mm`
- Preserved lens seat: `25.5 mm`, z `649.6 to 650.0 mm`
- Rebuilt transition chamfer: `25.5 -> 30.0 mm` over `2.25 mm`
- Pitch: `0.8 mm`
- Tooth height, radial: `0.2 mm`
- Tooth base: `0.8 mm`
- Runout extra at each end: `0.4 mm`

This is not a C-mount conversion. It keeps the OpenHI 30 mm family and tightens the positive-Z female receiver from the old 30.2 mm start/root to a 30.0 mm pilot, with a 30.4 mm groove cutter. The lens-side 25.5 mm seat is preserved and the 45 degree chamfer is shortened to land on the new 30.0 mm pilot.

## Geometry Summary

- Source bbox: `40.7340002 x 40.7340002 x 85.367000205 mm`
- Variant bbox: `40.7340002 x 40.7340002 x 85.367000205 mm`
- Source solids: `1`
- Variant solids: `1`
- Export round-trip bbox difference: `[0.0, 0.0, 0.0] mm`

The source is a single imported B-rep solid from `Lens B holder.step`. STEP export and re-import can shift reported tolerance boxes by microns; this build treats differences under 0.01 mm as preserved.

## Build Method

1. Import `Lens B holder.step`.
2. Union a 32 mm fill cylinder into the old positive-Z receiver only.
3. Preserve the 25.5 mm lens seat up to z=650.0 mm.
4. Re-cut a 45 degree transition chamfer from 25.5 mm to 30.0 mm.
5. Cut a 30.0 mm smooth pilot bore from the adjusted chamfer end.
6. Subtract a 30.4 mm max-diameter helical thread cutter.

The helical cutter is built as a stable X-axis sweep and then rotated into the Lens B Z-axis frame. This avoids a STEP export failure mode where a direct Z-axis helical cutter can leave a loose cutter-like fragment even though the in-memory boolean looks correct.

## Artifacts

| Artifact | Path |
| --- | --- |
| assembly_step | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit.step` |
| assembly_stl | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit.stl` |
| fill_cylinder_step | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_old_receiver_fill_cylinder.step` |
| transition_chamfer_cutter_step | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_transition_chamfer_cutter.step` |
| pilot_bore_cutter_step | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_pilot_bore_cutter.step` |
| thread_cutter_step | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_female_thread_cutter_30p4.step` |
| source_copy_step | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_source_copy.step` |
| render_png | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_render.png` |
| thread_detail_render_png | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_thread_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_b_holder_receiver_30p0_30p4_print_fit.blend` |
| manifest_json | `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/build_openhi_lens_b_holder_receiver_30p0_30p4_print_fit.py
blender --background --python cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/render_openhi_lens_b_holder_receiver_30p0_30p4_print_fit.py
```

## Fit Note

Use this when the old 30.2 mm female receiver is too loose on the newer printer. If it is too tight, make a sibling with a 30.1 or 30.2 mm pilot and/or a 30.5 mm cutter.
