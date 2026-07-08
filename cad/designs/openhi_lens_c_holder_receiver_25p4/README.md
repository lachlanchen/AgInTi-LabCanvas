# OpenHI Lens C Holder Receiver 25.4

This is a sibling proof-of-concept variant of the exact Lens C holder regeneration. It keeps the left `Thread BS` solid unchanged, fills the old positive-X receiver, then cuts a new nominal 25.4 mm female/internal receiver.

## Correction Note

This folder is a C-mount-sized experiment only. It is not the corrected OpenHI Lens C print-fit task. For the actual Lens C holder adjustment, use `openhi_lens_c_holder_receiver_30p0_30p4_print_fit`, which keeps the OpenHI 30 mm thread family and changes the positive-X receiver to a 30.0 mm pilot plus 30.4 mm groove cutter.

## Thread Definition

- Nominal female major/max diameter: `25.4 mm`
- Smooth pilot bore before thread subtraction: `24.6 mm`
- Thread cutter max diameter: `25.4 mm`
- Pitch: `0.8 mm`
- Tooth height: `0.4 mm`
- Tooth base: `0.8 mm`
- Runout extra at each end: `0.4 mm`

Here 25.4 mm means the nominal internal thread max/major diameter after subtracting the thread cutter. The smooth pilot bore is 24.6 mm.

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
4. Cut a 24.6 mm smooth pilot bore.
5. Subtract a 25.4 mm max-diameter helical thread cutter.
6. Recombine the preserved `Thread BS` solid with the modified body.

## Artifacts

| Artifact | Path |
| --- | --- |
| assembly_step | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4.step` |
| assembly_stl | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4.stl` |
| modified_body_step | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_modified_body.step` |
| modified_body_stl | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_modified_body.stl` |
| fill_cylinder_step | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_old_receiver_fill_cylinder.step` |
| pilot_bore_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_pilot_bore_cutter.step` |
| thread_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_female_thread_cutter_25p4.step` |
| inspection_cutaway_step | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_inspection_cutaway.step` |
| inspection_cutaway_stl | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_inspection_cutaway.stl` |
| render_png | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_render.png` |
| receiver_detail_render_png | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_receiver_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/openhi_lens_c_holder_receiver_25p4.blend` |
| manifest_json | `cad/designs/openhi_lens_c_holder_receiver_25p4/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_lens_c_holder_receiver_25p4/build_openhi_lens_c_holder_receiver_25p4.py
blender --background --python cad/designs/openhi_lens_c_holder_receiver_25p4/render_openhi_lens_c_holder_receiver_25p4.py
```

## Fit Note

This is a true-nominal proof of concept. For a looser printed female thread, make a sibling variant with a larger cutter max diameter such as 25.6 or 25.8 mm.
