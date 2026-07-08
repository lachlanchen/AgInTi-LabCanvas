# OpenHI Lens C Holder Receiver 30.0/30.4 Print Fit

This is a sibling proof-of-concept variant of the exact Lens C holder regeneration. It keeps the left `Thread BS` solid unchanged, fills the old positive-X OpenHI receiver, then cuts a tighter 30.0/30.4 mm female print-fit receiver.

## Thread Definition

- Female smooth pilot/start diameter: `30.0 mm`
- Female groove/thread-cutter max diameter: `30.4 mm`
- Preserved lens seat: `25.5 mm`, x `324.5 to 325.0 mm`
- Rebuilt transition chamfer: `25.5 -> 30.0 mm` over `2.25 mm`
- Pitch: `0.8 mm`
- Tooth height, radial: `0.2 mm`
- Tooth base: `0.8 mm`
- Runout extra at each end: `0.4 mm`

This is not a C-mount change. It follows the OpenHI printed M30-style fit: the female starts as a 30.0 mm smooth bore, then a 30.4 mm max-diameter thread cutter creates the groove. The unchanged male side is treated as about 29.8 mm at the base and about 30.2 mm at the printed crest, leaving about 0.2 mm diameter clearance in the mating pair.

## Geometry Summary

- Source bbox: `50.000000204 x 40.0000002 x 40.0000002 mm`
- Variant bbox: `50.000001754 x 40.0 x 40.0 mm`
- Source solids: `2`
- Variant solids: `2`
- Preserved left solid bbox: `5.904183794 x 30.600000199 x 30.6000002 mm`
- Export round-trip bbox difference: `[1.55e-06, 2e-07, 2e-07] mm`
- Left thread export bbox difference: `[0.004183594, 0.0, 0.0] mm`

The left `Thread BS` solid is reused unchanged by construction. STEP export and re-import can slightly expand reported B-rep tolerance boxes; this build treats differences under 0.01 mm as preserved for the proof of concept.

## Build Method

1. Import `Lens C holder.step`.
2. Keep solid 0 (`Thread BS`) unchanged.
3. Union a 32 mm fill cylinder into solid 1 over the old positive-X receiver.
4. Preserve the lens seat up to x=325.0 mm.
5. Re-cut a 45 degree transition chamfer from 25.5 mm to 30.0 mm.
6. Cut a 30.0 mm smooth pilot bore from the adjusted chamfer end.
7. Subtract a 30.4 mm max-diameter helical thread cutter.
8. Recombine the preserved `Thread BS` solid with the modified body.

## Artifacts

| Artifact | Path |
| --- | --- |
| assembly_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit.step` |
| assembly_stl | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit.stl` |
| modified_body_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_modified_body.step` |
| modified_body_stl | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_modified_body.stl` |
| fill_cylinder_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_old_receiver_fill_cylinder.step` |
| transition_chamfer_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_transition_chamfer_cutter.step` |
| pilot_bore_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_pilot_bore_cutter.step` |
| thread_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_female_thread_cutter_30p4.step` |
| inspection_cutaway_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_inspection_cutaway.step` |
| inspection_cutaway_stl | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_inspection_cutaway.stl` |
| render_png | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_render.png` |
| receiver_detail_render_png | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_receiver_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_print_fit.blend` |
| manifest_json | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/build_openhi_lens_c_holder_receiver_30p0_30p4_print_fit.py
blender --background --python cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit/render_openhi_lens_c_holder_receiver_30p0_30p4_print_fit.py
```

## Fit Note

Use this when the old 30.2 mm female start diameter is too loose on the newer printer. If it is still tight after printing, make a sibling with a 30.1 or 30.2 mm pilot and/or a 30.5 mm cutter.
