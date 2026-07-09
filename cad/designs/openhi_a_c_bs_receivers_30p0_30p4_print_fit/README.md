# OpenHI A+C+BS Lower Receiver 30.0/30.4 Print Fit

This sibling design tightens the lower OpenHI 30 mm female receiver start in `A+ C + BS.step` while preserving the exact source body envelope and the original beam-splitter-side receiver.

## Thread Definition

- Old measured receiver start/root diameter: `30.2 mm`
- New smooth pilot/start diameter: `30.0 mm`
- New groove/thread-cutter max diameter: `30.4 mm`
- Pitch: `0.8 mm`; radial tooth height: `0.2 mm`; tooth base: `0.8 mm`

## Changed Regions

- Bottom/away-from-BS receiver: rebuilt from the 40 mm mouth to the preserved 25.5 mm lens-seat transition.
- BS/B-side receiver: preserved exactly from the OpenHI source STEP to avoid adding foreign surfaces inside the beam-splitter pocket.

The vertical receiver is rebuilt with fill bodies shaped close to the old mouth/thread void, not a broad oversized tube. The horizontal BS/B-side receiver is left untouched because both full-cylinder fill and annular wall-fill approaches created unstable or visible foreign B-rep surfaces in the beam-splitter opening. Preserving that side keeps the optical pocket clean.

## Validation

- Source bbox: `40.0000002 x 40.0000002 x 84.900000204 mm`
- Variant bbox: `40.0000002 x 40.0000002 x 84.900000202 mm`
- Overall bbox size difference: `[0.0, 0.0, 2e-09] mm`
- Source solids: `1`; variant solids: `1`
- Old 30.2 mm vertical faces remaining in modified scan: `0`
- Old 30.2 mm horizontal faces preserved in modified scan: `1`
- Exposed mid-diameter fill candidate faces: `0`
- New 30.0 mm cylinder faces found: `[(3, 30.0, {'min': [240.0, 195.0, 540.0], 'max': [270.0, 225.0, 547.75], 'size': [30.0, 30.0, 7.75]})]`

This is still a surgical B-rep variant. Inspect the exported cutter files and renders before printing. A previous full-cylinder horizontal fill left a visible foreign strip in the beam-splitter opening, and the annular retry was unstable in OCCT; this build intentionally does not edit that BS-side receiver.

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
