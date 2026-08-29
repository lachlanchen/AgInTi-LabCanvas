# OpenHI Same-Lens 4f System: GLA11-025-050-A plano-convex lens

## Use This

- `USE_THIS_gla11_025_050_openhi_4f_assembly.step`: six mechanical parts plus three lens copies and a beam-splitter reference.
- `artifacts/parts/`: separate STEP, STL, and 3MF files for A, A+C+BS, B, C, Lens B holder, and Lens C holder.
- `artifacts/gla11_025_050_lens.step`: standalone lens model.
- `artifacts/manifest.json`: dimensions, source identity, assembly transforms, focal datums, and validation.

## Optical Layout

All three arms use the same `GLA11-025-050-A plano-convex lens` lens. The beam-splitter center is the fixed datum `(255, 210, 600) mm`. The CAD places the A, B, and C holder contact planes one catalog EFL from that datum: `50.00000 mm`. Therefore A-B and A-C nominal principal-plane separations are `2f = 100.00000 mm` under the source OpenHI thin-lens convention. Manufacturer BFL: `46.500 mm`.

For the plano-convex variants, all plane faces point inward toward the beam splitter, as requested. The manifest records the BFL-versus-EFL difference so a bench test can tune the final axial position rather than hiding a thick-lens assumption.

## Lens Fit

- nominal lens diameter: `25.000 mm`;
- holder pocket: `25.250 mm`;
- clear aperture: `23.500 mm`;
- modeled mechanical edge thickness: `2.070 mm`;
- retaining axial envelope at the actual support radius: `2.463 mm`;
- axial pocket allowance: `0.200 mm`;
- female threads: `29.8/30.6 mm`, pitch `0.8 mm`, bounded at both ends.

The holder side supplies the flat locating shoulder. A/B/C retain from the opposite side. The 45-degree diameter transition is on the A/B/C-facing receiver side, preserving the original OpenHI design philosophy.

All optical pockets are centered at X/Y = `255/210 mm`. The B holder keeps its source outer-skin offset at X = `254.633 mm`, but that exterior asymmetry no longer shifts the lens, aperture, transition, or thread.

## Prescription Status

`manufacturer-complete`. Manufacturer dimensions; plane face is oriented toward the beam splitter.

This is a mechanically buildable CAD reconstruction. JH042/JH036 require a vendor optical drawing before the internal cemented interface can be certified as an exact optical prescription.

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_4f_gla11_025_050_same_lens/build_gla11_025_050_openhi_4f.py
blender --background --python cad/tools/render_openhi_same_lens_4f.py -- --design-dir cad/designs/openhi_4f_gla11_025_050_same_lens
```
