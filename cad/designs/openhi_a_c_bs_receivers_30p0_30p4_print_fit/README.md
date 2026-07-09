# OpenHI A+C+BS Receivers 30.0/30.4 Print Fit

This sibling design tightens both OpenHI 30 mm female receiver starts in `A+ C + BS.step` while preserving the exact source body envelope.

## Thread Definition

- Old measured receiver start/root diameter: `30.2 mm`
- New smooth pilot/start diameter: `30.0 mm`
- New groove/thread-cutter max diameter: `30.4 mm`
- Pitch: `0.8 mm`; radial tooth height: `0.2 mm`; tooth base: `0.8 mm`

## Changed Regions

- Bottom/away-from-BS receiver: rebuilt from the 40 mm mouth to the preserved 25.5 mm lens-seat transition.
- BS/B-side receiver: old internal receiver is filled inside the existing envelope, then re-cut as a 30.0 mm pilot with a bounded 30.4 mm thread at the outer end.

The vertical receiver is rebuilt with fill bodies shaped close to the old mouth/thread void, not a broad oversized tube. The horizontal BS/B-side receiver uses a 30.2 mm pilot fill and a short 31.0 mm thread-zone fill before re-cutting the 30.0 mm pilot and bounded 30.4 mm thread. This avoids exposed 32 mm fill-tube faces.

## Validation

- Source bbox: `40.0000002 x 40.0000002 x 84.900000204 mm`
- Variant bbox: `40.000000201 x 40.0000002 x 84.900000202 mm`
- Overall bbox size difference: `[1e-09, 0.0, 2e-09] mm`
- Source solids: `1`; variant solids: `1`
- Old 30.2 mm vertical faces remaining in modified scan: `0`
- Old 30.2 mm horizontal faces remaining in modified scan: `0`
- Exposed mid-diameter fill candidate faces: `0`
- New 30.0 mm cylinder faces found: `[(3, 30.0, {'min': [240.0, 195.0, 540.0], 'max': [270.0, 225.0, 547.75], 'size': [30.0, 30.0, 7.75]}), (13, 30.0, {'min': [246.9999999, 194.999999884, 584.9999999], 'max': [270.46668373, 225.0000001, 615.0000001], 'size': [23.46668383, 30.000000216, 30.0000002]}), (27, 30.0, {'min': [270.33340513, 194.999999895, 584.999999891], 'max': [271.266677102, 225.0000001, 615.000000098], 'size': [0.933271973, 30.000000205, 30.000000207]}), (40, 30.0, {'min': [271.133315922, 194.9999999, 584.999999923], 'max': [272.066697814, 225.0000001, 615.000000098], 'size': [0.933381892, 30.0000002, 30.000000175]}), (41, 30.0, {'min': [271.933322627, 194.99999974, 584.99999987], 'max': [272.866605793, 225.0000001, 615.0000001], 'size': [0.933283166, 30.00000036, 30.00000023]}), (42, 30.0, {'min': [272.733302857, 194.999999898, 584.999999887], 'max': [273.666700732, 225.0000001, 615.000000116], 'size': [0.933397875, 30.000000202, 30.000000229]}), (43, 30.0, {'min': [273.533393888, 194.9999999, 584.9999999], 'max': [274.466654387, 225.0000001, 615.000000101], 'size': [0.933260499, 30.0000002, 30.000000201]}), (44, 30.0, {'min': [274.333299188, 194.999999892, 584.999999904], 'max': [275.000000101, 225.0000001, 615.0000001], 'size': [0.666700914, 30.000000208, 30.000000196]})]`

This is still a surgical B-rep variant. Inspect the exported cutter files and renders before printing; if the BS/B-side receiver feels too tight, create a sibling with 30.1 mm pilot or 30.5 mm cutter. A previous broad-fill attempt exposed 32 mm fill surfaces; this build intentionally avoids those faces.

## Artifacts

| Artifact | Path |
| --- | --- |
| assembly_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit.step` |
| assembly_stl | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit.stl` |
| vertical_front_mouth_fill_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_vertical_front_mouth_fill.step` |
| vertical_internal_fill_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_vertical_internal_fill.step` |
| vertical_front_mouth_cutter_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_vertical_front_mouth_cutter.step` |
| vertical_pilot_bore_cutter_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_vertical_pilot_bore_cutter.step` |
| vertical_thread_cutter_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_vertical_thread_cutter.step` |
| vertical_transition_chamfer_cutter_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_vertical_transition_chamfer_cutter.step` |
| horizontal_pilot_fill_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_horizontal_pilot_fill.step` |
| horizontal_thread_fill_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_horizontal_thread_fill.step` |
| horizontal_pilot_bore_cutter_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_horizontal_pilot_bore_cutter.step` |
| horizontal_thread_cutter_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_horizontal_thread_cutter.step` |
| inspection_cutaway_step | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_inspection_cutaway.step` |
| inspection_cutaway_stl | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_inspection_cutaway.stl` |
| render_png | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_render.png` |
| receiver_detail_render_png | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_receiver_detail_render.png` |
| inspection_cutaway_render_png | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_inspection_cutaway_render.png` |
| blend | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit.blend` |
| manifest_json | `cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/manifest.json` |

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/build_openhi_a_c_bs_receivers_30p0_30p4_print_fit.py
blender --background --python cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/render_openhi_a_c_bs_receivers_30p0_30p4_print_fit.py
```
