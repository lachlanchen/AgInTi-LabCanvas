# OpenHI Same-Lens 4f System: GLA11-025-050-A plano-convex lens

## Use This

- `USE_THIS_gla11_025_050_openhi_4f_assembly.step`: six mechanical parts plus three lens copies and a beam-splitter reference.
- `artifacts/parts/`: separate STEP, STL, and 3MF files for A, A+C+BS, B, C, Lens B holder, and Lens C holder.
- `artifacts/gla11_025_050_lens.step`: standalone lens model.
- `artifacts/manifest.json`: dimensions, source identity, assembly transforms, focal datums, and validation.
- `artifacts/renders/openhi_4f_spatial_exploded.png`: spatial view with all mechanical parts, lenses, and beam splitter separated along their mating directions.
- `artifacts/renders/openhi_4f_print_parts_layout.png`: exact orientations used by the separate STL/3MF print files.
- `artifacts/renders/openhi_4f_a_input_receiver_section.png`: A-only half section proving the internal source receiver and lifted bore transition.
- `artifacts/renders/openhi_4f_a_lens_cavity_section.png`: A/A+C+BS half section with the installed lens B-rep at its checked optical datum.
- `runs/run-4-a-input-receiver-optical-vertex-lens-clearance-print-ready-20260901T040031Z/`: checked one-object print files and the matching Nutstore handoff.

## Optical Layout

All three arms use the same `GLA11-025-050-A plano-convex lens` lens. The beam-splitter center is the fixed datum `(255, 210, 600) mm`. The CAD places each inward optical-axis surface vertex exactly one catalog EFL from that datum: `50.00000 mm`. Therefore the inward A-B and A-C surface-vertex paths are `2f = 100.00000 mm` under the source OpenHI thin-lens convention. Manufacturer BFL: `46.500 mm`.

The optical vertex and the annular support seat are separate datums. At the support radius, this lens's inward surface is `0.000000 mm` from its axis vertex. Each holder seat is offset by that sag, while the matching A/B/C cap leaves the full `2.462878 mm` support-to-support lens envelope plus `0.20 mm` tightening travel. Thus a fully inserted threaded pair captures the real finite lens without adding half or all of the lens thickness again to the `2f` or `4f` optical distance.

The complete physical A-to-B and A-to-C outer-end paths are both `204.60000 mm = 4f + 4.6 mm`. The `4.6 mm` allowance is measured from the accepted ST018 assembly, not guessed: the A outer end contributes `f + 0.2 mm` and each output end contributes `f + 4.4 mm`. Thread length overlaps its receiver and is not added again to this path.

For the plano-convex variants, all plane faces point inward toward the beam splitter, as requested. The manifest records the BFL-versus-EFL difference so a bench test can tune the final axial position rather than hiding a thick-lens assumption.

## Lens Fit

- nominal lens diameter: `25.000 mm`;
- holder pocket: `25.250 mm`;
- radial pocket clearance per side: `0.125 mm`;
- clear aperture: `23.500 mm`;
- holder/cap support lands: `0.875/0.750 mm` radial;
- minimum holder wall beside the lens pocket: `7.375 mm`;
- modeled mechanical edge thickness: `1.662 mm`;
- retaining axial envelope at the actual support radius: `2.463 mm`;
- retainer tightening travel: `0.200 mm`;
- female threads: `29.8/30.6 mm`, pitch `0.8 mm`, `7.75 mm` bounded engagement;
- matching male lens threads: `29.6/30.4 mm` root/crest;
- root and crest radial thread clearance: `0.100/0.100 mm`;
- B optical axis: `X = 254.633 mm`, intentionally `-0.367 mm` from the A/beam-splitter datum.

The central interface map is deliberately not uniform: the preserved A+C+BS side/C female remains `29.6/30.4 mm`; its lower/A female is `29.8/30.6 mm`; both regenerated B/C lens-side females are `29.8/30.6 mm`; and the Lens C holder beam-splitter-side male remains the unchanged source `29.8/30.6 mm` root/crest. The central C pair therefore has `0.2 mm` nominal diametric interference. It is a preserved tight printed source fit, not a zero-clearance CAD pair. The three newly regenerated lens-retainer pairs are the clearance fits.

The output thread also preserves the source OpenHI printed profile (`24.4 mm` root, `25.2 mm` crest, `0.8 mm` pitch). It is intentionally not relabeled as exact standard `1"-32 UN` C-mount (`25.4 mm`, `0.79375 mm` pitch).

The A input end now preserves the exact internal female receiver cavity from the original `OpenHI_STEP/A.step`: `12.474 mm` insertion depth, `25.0 mm` pilot, and `25.8 mm` groove envelope. Its mating flange seats at the A outer face. The entire receiver depth remains inside the A arm envelope, followed by a 45-degree transition to the lens clear aperture; it is not a second seat-height term in the focal chain.

The holder side supplies the flat locating shoulder. A/B/C retain from the opposite side. The 45-degree diameter transition is on the A/B/C-facing receiver side, preserving the original OpenHI design philosophy.

The A and C axes use the beam-splitter datum. The complete B chain, including holder bore, pocket, lens, retainer, and camera thread, preserves the accepted source axis at `X = 254.633 mm`; it must not be recentered to `255 mm`.

The final validator probes a centered `4.0 mm` cylinder through the complete A, B, and C mechanical paths. It also probes a `29.4 mm` smooth core across the A+C+BS C receiver. All probes must have zero solid overlap. This explicitly prevents the earlier `0.10 mm` fusion membrane from returning at the C receiver.

## Prescription Status

`manufacturer-complete`. Manufacturer dimensions; plane face is oriented toward the beam splitter.

This is a mechanically buildable CAD reconstruction. JH042/JH036 require a vendor optical drawing before the internal cemented interface can be certified as an exact optical prescription.

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_4f_gla11_025_050_same_lens/build_gla11_025_050_openhi_4f.py
blender --background --python cad/tools/render_openhi_same_lens_4f.py -- --design-dir cad/designs/openhi_4f_gla11_025_050_same_lens
```
