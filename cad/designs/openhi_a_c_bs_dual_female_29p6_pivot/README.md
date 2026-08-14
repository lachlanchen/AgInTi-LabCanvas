# OpenHI A+C+BS Dual 29.6 mm Female-Pivot Variant

## Use This File

`USE_THIS_openhi_a_c_bs_dual_female_29p6_pivot.step`

For a direct mesh handoff, use `USE_THIS_openhi_a_c_bs_dual_female_29p6_pivot.3mf`.

This is a sibling tight-fit variant of only `A+ C + BS.step`. The source STEP, `OpenHI.shapr`, `A.step`, and `C.step` are untouched.

## Requested Change

- Lower/A-branch female pivot: `30.2 -> 29.6 mm`.
- Side/C-branch female pivot: `30.2 -> 29.6 mm`.
- Thread pitch remains `0.8 mm`.
- Radial tooth height remains `0.4 mm`, so both groove diameters are `30.4 mm`.
- Hand remains right-hand and the `0.8 mm` tooth base remains unchanged.

## Preserved Geometry

The builder imports the authoritative source STEP and modifies only the two female receiver interiors. It preserves the outer body, BS slope and pocket, axes, center bore, pin holes, `25.5 mm` lens seat, and all unrelated geometry. The lower mouth and lens-seat transitions remain source-style straight `45 degree` chamfers. Their axial endpoints move only as required to meet the smaller `29.6 mm` pilot without introducing a shelf or broken shell.

The helix is constructed with extra runout at both ends and clipped back to the exact receiver interval. This prevents the thread from protruding through the mouth, transition, or adjacent body.

## Fit Warning

This is intentionally much tighter than the original pair. The unchanged A top male is approximately `29.8/30.6 mm` root/crest, while this requested receiver is `29.6/30.4 mm`. That is about `0.2 mm diametral interference` at both corresponding envelopes. The side mating interface can have the same issue depending on which unchanged C-side component is installed. Print a short fit coupon or test one receiver before committing to the complete optical assembly.

## Validation

- Source and output bbox: `[40.0, 40.0, 84.9]` mm; preserved: `True`.
- All material changes are confined to the two receiver envelopes: `True`.
- One solid: `True`; OCCT valid after STEP round trip: `True`.
- Lower receiver measured `29.6/30.4 mm`: `True`.
- Side receiver measured `29.6/30.4 mm`: `True`.
- Thread runouts remain bounded: `True`.
- Lower 45-degree chamfers preserved: `True`.
- Render mesh is one watertight, consistently wound component: `True`.
- Welded 3MF reopens as one watertight, consistently wound component with matching bounds: `True`.

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_a_c_bs_dual_female_29p6_pivot/build_openhi_a_c_bs_dual_female_29p6_pivot.py
blender --background --python cad/designs/openhi_a_c_bs_dual_female_29p6_pivot/render_openhi_a_c_bs_dual_female_29p6_pivot.py
```
