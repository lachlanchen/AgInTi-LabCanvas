# OpenHI Same-Lens 4f System: JH042 cemented doublet

## Use This

- `USE_THIS_jh042_openhi_4f_assembly.step`: six mechanical parts plus three lens copies and a beam-splitter reference.
- `artifacts/parts/`: separate STEP, STL, and 3MF files for A, A+C+BS, B, C, Lens B holder, and Lens C holder.
- `artifacts/jh042_lens.step`: standalone lens model.
- `artifacts/manifest.json`: dimensions, source identity, assembly transforms, focal datums, and validation.

## Optical Layout

All three arms use the same `JH042 cemented doublet` lens. The beam-splitter center is the fixed datum `(255, 210, 600) mm`. The CAD places the A, B, and C holder contact planes one catalog EFL from that datum: `27.48499 mm`. Therefore A-B and A-C nominal principal-plane separations are `2f = 54.96998 mm` under the source OpenHI thin-lens convention. The catalog does not provide BFL/principal-plane locations.

The complete physical A-to-B and A-to-C outer-end paths are both `114.53996 mm = 4f + 4.6 mm`. The `4.6 mm` allowance is measured from the accepted ST018 assembly, not guessed: the A outer end contributes `f + 0.2 mm` and each output end contributes `f + 4.4 mm`. Thread length overlaps its receiver and is not added again to this path.

For the plano-convex variants, all plane faces point inward toward the beam splitter, as requested. The manifest records the BFL-versus-EFL difference so a bench test can tune the final axial position rather than hiding a thick-lens assumption.

## Lens Fit

- nominal lens diameter: `22.000 mm`;
- holder pocket: `22.250 mm`;
- clear aperture: `20.500 mm`;
- modeled mechanical edge thickness: `6.537 mm`;
- retaining axial envelope at the actual support radius: `6.803 mm`;
- axial pocket allowance: `0.200 mm`;
- female threads: `29.8/30.6 mm`, pitch `0.8 mm`, `7.75 mm` bounded engagement;
- matching male lens threads: `29.6/30.4 mm` root/crest;
- B optical axis: `X = 254.633 mm`, intentionally `-0.367 mm` from the A/beam-splitter datum.

The holder side supplies the flat locating shoulder. A/B/C retain from the opposite side. The 45-degree diameter transition is on the A/B/C-facing receiver side, preserving the original OpenHI design philosophy.

The A and C axes use the beam-splitter datum. The complete B chain, including holder bore, pocket, lens, retainer, and camera thread, preserves the accepted source axis at `X = 254.633 mm`; it must not be recentered to `255 mm`.

## Prescription Status

`mechanically-constrained-assumption`. Catalog gives total thickness and three radius magnitudes but not signed radii or the two element center thicknesses. Signs and the 2.5/6.0 mm split are explicit mechanical reconstruction assumptions.

This is a mechanically buildable CAD reconstruction. JH042/JH036 require a vendor optical drawing before the internal cemented interface can be certified as an exact optical prescription.

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_4f_jh042_same_lens/build_jh042_openhi_4f.py
blender --background --python cad/tools/render_openhi_same_lens_4f.py -- --design-dir cad/designs/openhi_4f_jh042_same_lens
```
