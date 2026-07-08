# OpenHI Lens C Holder Receiver 30.0/30.4 Clean Rebuild

This sibling variant fixes the messy receiver in the earlier proof-of-concept. The old version filled the original female thread and then re-cut it, which could leave a small internal shell/sliver inside the thread. This version trims the old receiver away at the lens-seat plane and rebuilds the positive-X receiver as clean geometry.

## Thread Definition

- Female smooth pilot/start diameter: `30.0 mm`
- Female groove/thread-cutter max diameter: `30.4 mm`
- Preserved lens seat: `25.5 mm`, x `324.5 to 325.0 mm`
- Rebuilt lens-side chamfer: `25.5 -> 30.0 mm` over `2.25 mm`
- Threaded section: x `327.25 to 335.9 mm`
- Pitch: `0.8 mm`; tooth height: `0.2 mm`; tooth base: `0.8 mm`
- Front mouth lead-in: `30.0 -> 40.0 mm`, x `336.0 to 340.0 mm`

## Clean-Rebuild Method

1. Import `Lens C holder.step`.
2. Preserve the left `Thread BS` solid unchanged.
3. Trim the main body at x=325.0 mm, preserving the lens seat up to that plane.
4. Build a new 40 mm OD receiver blank from x=325.0 to 340.0 mm.
5. Cut the lens-side 25.5 -> 30.0 mm chamfer.
6. Cut the bounded 30.4 mm helical thread cutter.
7. Cut the 30.0 mm pilot bore and front mouth lead-in.
8. Union the clean receiver to the trimmed body.

Trim the imported body at x=325.0, preserve the 25.5 mm lens seat, then union a new clean receiver. The helical cutter is swept with half-pitch runout but clipped to x=327.25..335.9, so no tooth crosses into the lens-side chamfer. The front mouth chamfer starts at x=336.0 after the full threaded section.

## Validation

- Source bbox: `50.000000204 x 40.0000002 x 40.0000002 mm`
- Variant bbox: `50.000001754 x 40.0000002 x 40.0000002 mm`
- Source solids: `2`; variant solids: `2`
- Modified body solids: `1`
- No exposed 32 mm fill-shell face: `True`
- No B-spline before thread start: `True`
- Thread B-spline face count: `2`
- Overall bbox size difference from source: `[1.55e-06, 0.0, 0.0] mm`

The design intentionally changes only the positive-X receiver internals and cleanly rebuilds that end. The front mouth lead-in begins after the full threaded section, so the helical cutter does not cross into the lens-side chamfer.

## Artifacts

| Artifact | Path |
| --- | --- |
| assembly_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild.step` |
| assembly_stl | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild.stl` |
| modified_body_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_modified_body.step` |
| modified_body_stl | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_modified_body.stl` |
| preserved_thread_bs_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_preserved_thread_bs.step` |
| trimmed_body_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_trimmed_body.step` |
| clean_receiver_body_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_clean_receiver_body.step` |
| receiver_outer_blank_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_receiver_outer_blank.step` |
| transition_chamfer_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_transition_chamfer_cutter.step` |
| pilot_bore_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_pilot_bore_cutter.step` |
| thread_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_female_thread_cutter_30p4.step` |
| front_mouth_chamfer_cutter_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_front_mouth_chamfer_cutter.step` |
| inspection_cutaway_step | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_inspection_cutaway.step` |
| inspection_cutaway_stl | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_inspection_cutaway.stl` |
| render_png | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_render.png` |
| receiver_detail_render_png | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_receiver_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild.blend` |
| manifest_json | `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/build_openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild.py
blender --background --python cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/render_openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild.py
```
